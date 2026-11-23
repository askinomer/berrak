"""Berrak canlı test betiği.

Gerçek Gemini ve arama servisleriyle 5 konu ve 1 yapıştırılmış metin dener.
Ayrıca seviye deneyi yapar: "Fotosentez nedir?" konusunun AYNI kaynaklarını
üç okuma seviyesinde ayrı ayrı sadeleştirir (yeni arama yapılmaz).

Her sonucu HTML sayfası olarak, tüm ölçümleri de bir JSON dosyası olarak
'canli_test_sonuclari' klasörüne kaydeder ve hepsini tek bir zip dosyasında toplar.

Kullanım (proje klasöründe):
    python canli_test.py

Anahtarlar şu sırayla aranır:
    1. Ortam değişkenleri: GEMINI_API_KEY, TAVILY_API_KEY
    2. .streamlit/secrets.toml dosyası
Tavily anahtarı yoksa arama DuckDuckGo ile yapılır.
Anahtarlar sonuç dosyalarına YAZILMAZ.
"""

from __future__ import annotations

import json
import os
import platform
import re
import statistics
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from berrak import __version__
from berrak.demo import DEMO_ORIGINAL
from berrak.evaluation import number_grounding, rule_compliance
from berrak.pipeline import run_sources, run_text, run_topic
from berrak.prompts import LEVELS
from berrak.readability import analyze
from berrak.render import DisplaySettings, render_html

ROOT = Path(__file__).parent
OUT = ROOT / "canli_test_sonuclari"

# (konu, okuma seviyesi, kapsamlı arama)
KONULAR = [
    ("Fotosentez nedir?", "İlkokul", False),
    ("Deprem neden olur?", "Ortaokul", True),
    ("İklim değişikliği nedir?", "Ortaokul", False),
    ("Yapay zekâ nedir?", "Lise / Yetişkin", False),
    ("Kurtuluş Savaşı", "Lise / Yetişkin", False),
]
METIN_BASLIGI = "Yapıştırılan metin: fotosentez paragrafı"
# Seviye deneyi: bu konunun kaynakları diğer seviyelerde de sadeleştirilir
SEVIYE_KONUSU = "Fotosentez nedir?"
BEKLEME_SN = 6  # ücretsiz katmanın dakikalık istek sınırına takılmamak için


def load_keys() -> dict[str, str]:
    keys = {k: os.environ.get(k, "").strip() for k in ("GEMINI_API_KEY", "TAVILY_API_KEY")}
    secrets = ROOT / ".streamlit" / "secrets.toml"
    if secrets.exists():
        for line in secrets.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\s*(GEMINI_API_KEY|TAVILY_API_KEY)\s*=\s*["\']([^"\']*)["\']', line)
            if m and not keys[m.group(1)]:
                keys[m.group(1)] = m.group(2).strip()
    return keys


def slugify(text: str) -> str:
    # "İ".lower() → "i" + birleşik nokta (U+0307); nokta atılmazsa "İlkokul" → "i-lkokul" olur
    text = text.lower().replace("̇", "").translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40] or "sonuc"


def redact(text: str) -> str:
    """Hata mesajlarında anahtar varsa gizler."""
    text = re.sub(r"(key=|AIza)[\w-]+", r"\1***", text)
    return re.sub(r"tvly-[\w-]+", "tvly-***", text)


def metrics(report) -> dict:
    d = report.as_dict()
    d.pop("long_sentences", None)
    return d


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 1) if values else None


def main() -> None:
    keys = load_keys()
    if not keys["GEMINI_API_KEY"] or keys["GEMINI_API_KEY"].startswith("buraya"):
        sys.exit(
            "GEMINI_API_KEY bulunamadı.\n"
            "Ücretsiz anahtar al: https://aistudio.google.com/apikey\n"
            "Sonra .streamlit/secrets.toml dosyasına yaz veya şunu çalıştır:\n"
            '    export GEMINI_API_KEY="anahtarın"'
        )

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    engine_note = "Tavily" if keys["TAVILY_API_KEY"] else "DuckDuckGo (Tavily anahtarı yok)"
    print(f"Berrak canlı test · arama: {engine_note}\n")

    jobs = [("konu", t, lvl, deep) for t, lvl, deep in KONULAR]
    jobs.append(("metin", METIN_BASLIGI, "Ortaokul", False))
    base_level = next((lvl for t, lvl, _ in KONULAR if t == SEVIYE_KONUSU), None)
    if base_level:
        jobs += [("seviye", SEVIYE_KONUSU, lvl, False) for lvl in LEVELS if lvl != base_level]

    runs, html_files, base_result = [], [], None
    for i, (kind, title, level, deep) in enumerate(jobs, 1):
        label = {"seviye": ", seviye deneyi: aynı kaynaklar"}.get(kind, ", kapsamlı arama" if deep else "")
        print(f"[{i}/{len(jobs)}] {title}  ({level}{label})", flush=True)
        t0 = time.time()
        try:
            if kind == "konu":
                r = run_topic(title, level, keys["GEMINI_API_KEY"], keys["TAVILY_API_KEY"] or None, deep=deep)
                if title == SEVIYE_KONUSU:
                    base_result = r
            elif kind == "metin":
                r = run_text(DEMO_ORIGINAL, level, keys["GEMINI_API_KEY"], title=title)
            else:
                if base_result is None:
                    raise RuntimeError(f"Seviye deneyi atlandı: '{SEVIYE_KONUSU}' araması başarısız oldu.")
                r = run_sources(base_result.sources, level, keys["GEMINI_API_KEY"], title,
                                engine=base_result.engine, queries=base_result.queries)
        except Exception as exc:  # bir konu başarısız olsa da diğerleri denensin
            msg = redact(str(exc))[:1500]
            print(f"    HATA: {msg}\n", flush=True)
            runs.append({"tur": kind, "baslik": title, "seviye": level, "kapsamli": deep,
                         "sure_sn": round(time.time() - t0, 1), "hata": msg})
            if i < len(jobs):
                time.sleep(BEKLEME_SN)
            continue

        sure = round(time.time() - t0, 1)
        limit = LEVELS[level]["max_words"]
        asan = analyze(r.content.plain_text(), long_sentence_limit=limit).long_sentences
        kurallar = rule_compliance(r.content, level, len(r.sources))
        sayilar = number_grounding(r.content, r.sources)
        html_file = OUT / f"{stamp}-{i:02d}-{slugify(title)}-{slugify(level)}.html"
        html_file.write_text(render_html(r.content, r.sources, DisplaySettings(), r.after, r.minutes),
                             encoding="utf-8")
        html_files.append(html_file)

        runs.append({
            "tur": kind, "baslik": title, "seviye": level, "kapsamli": deep, "sure_sn": sure,
            "model": r.model, "arama_motoru": r.engine, "sorgular": r.queries,
            "kaynaklar": [{"baslik": s.get("title", ""), "url": s.get("url", ""),
                           "karakter": len(s.get("content", "")), "metin": s.get("content", "")}
                          for s in r.sources],
            "once": metrics(r.before), "sonra": metrics(r.after),
            "cumle_siniri": limit, "siniri_asan_cumleler": asan,
            "kurallar": kurallar, "sayilar": sayilar,
            "okuma_suresi_dk": r.minutes, "html": html_file.name,
            "icerik": r.content.model_dump(),
        })
        print(f"    tamam · {sure} sn · model {r.model} · {r.engine}, {len(r.sources)} kaynak · "
              f"Ateşman {r.before.atesman:.0f} → {r.after.atesman:.0f} · "
              f"ort. cümle {r.before.avg_sentence_words} → {r.after.avg_sentence_words} kelime · "
              f"{limit} kelimeyi aşan cümle: {len(asan)} · "
              f"kaynak gösterilen birim: %{kurallar['kaynakli_birim_yuzde']} · "
              f"sayı: {sayilar['kaynakta_gecen']}/{sayilar['sayi']} kaynakta var\n", flush=True)
        if i < len(jobs):
            time.sleep(BEKLEME_SN)

    ok = [x for x in runs if "hata" not in x]
    summary = {
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "berrak_surumu": __version__,
        "python": platform.python_version(),
        "sistem": platform.platform(),
        "arama": engine_note,
        "basarili": len(ok),
        "toplam": len(runs),
        "calismalar": runs,
    }
    if ok:
        summary["ortalama"] = {
            "atesman_once": _mean(x["once"]["atesman"] for x in ok),
            "atesman_sonra": _mean(x["sonra"]["atesman"] for x in ok),
            "cumle_once": _mean(x["once"]["avg_sentence_words"] for x in ok),
            "cumle_sonra": _mean(x["sonra"]["avg_sentence_words"] for x in ok),
            "siniri_asan_cumle_yuzde": _mean(x["kurallar"]["siniri_asan_cumle_yuzde"] for x in ok),
            "kaynakli_birim_yuzde": _mean(x["kurallar"]["kaynakli_birim_yuzde"] for x in ok),
            "sure_sn": _mean(x["sure_sn"] for x in ok),
        }
        summary["toplamlar"] = {
            "sayi": sum(x["sayilar"]["sayi"] for x in ok),
            "kaynakta_gecen_sayi": sum(x["sayilar"]["kaynakta_gecen"] for x in ok),
            "gecersiz_kaynak_no": sum(x["kurallar"]["gecersiz_kaynak_no"] for x in ok),
        }

    out = OUT / f"{stamp}-sonuclar.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    zip_path = OUT / f"{stamp}-sonuclar.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in [out, *html_files]:
            z.write(f, f.name)

    print("=" * 60)
    print(f"{len(ok)}/{len(runs)} test başarılı.")
    if ok:
        a, t = summary["ortalama"], summary["toplamlar"]
        print(f"Ortalama Ateşman: {a['atesman_once']} → {a['atesman_sonra']}  ·  "
              f"ortalama cümle: {a['cumle_once']} → {a['cumle_sonra']} kelime  ·  "
              f"ortalama süre: {a['sure_sn']} sn")
        print(f"Seviye sınırını aşan cümle: %{a['siniri_asan_cumle_yuzde']}  ·  "
              f"kaynak gösterilen birim: %{a['kaynakli_birim_yuzde']}  ·  "
              f"kaynakta bulunan sayı: {t['kaynakta_gecen_sayi']}/{t['sayi']}")
    print(f"\nSonuç dosyası: {zip_path}")
    print("İçinde ölçümler (JSON) ve üretilen sayfalar (HTML) var. Sayfalar internetsiz de açılır.")


if __name__ == "__main__":
    main()
