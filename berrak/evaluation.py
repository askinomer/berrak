"""Sadeleştirme çıktısının kurallara uyumunu ve kaynaklara bağlılığını ölçen yardımcılar.

Canlı test betiği (canli_test.py) bu ölçümleri her konu için hesaplar.
Hepsi saf fonksiyonlardır; internete çıkmaz.
"""

from __future__ import annotations

import re

from .llm import BerrakIcerik
from .prompts import LEVELS
from .readability import split_sentences, words

CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
NUM_RE = re.compile(r"\d[\d.,]*\d|\d")


def _clean(text: str) -> str:
    return CITE_RE.sub("", BOLD_RE.sub(r"\1", text or ""))


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def numbers(text: str) -> set[str]:
    """Metindeki 2+ basamaklı sayılar (yıl, yüzde, ölçü). Nokta ve virgül yok sayılır."""
    out = set()
    for n in NUM_RE.findall(text or ""):
        digits = re.sub(r"\D", "", n)
        if len(digits) >= 2:
            out.add(digits)
    return out


def rule_compliance(c: BerrakIcerik, level: str, n_sources: int) -> dict:
    """Sistem prompt'undaki biçim kurallarına uyumu sayar."""
    cfg = LEVELS[level]
    limit = cfg["max_words"]

    sent_lens = [len(words(s)) for s in split_sentences(c.plain_text())]
    over = sum(1 for n in sent_lens if n > limit)
    paras = [p for b in c.bolumler for p in b.paragraflar]
    para_sents = [len(split_sentences(_clean(p))) for p in paras]
    para_bold = [len(BOLD_RE.findall(p)) for p in paras]

    # Bilgi taşıyan birimler: Kısaca maddeleri, paragraflar ve madde işaretli satırlar
    units = [u for u in [*c.kisaca, *paras, *[m for b in c.bolumler for m in b.maddeler]] if u.strip()]
    cited = sum(1 for u in units if CITE_RE.search(u))
    invalid = sum(
        1
        for u in units
        for m in CITE_RE.finditer(u)
        for n in re.findall(r"\d+", m.group(1))
        if not 1 <= int(n) <= n_sources
    )

    return {
        "cumle_sayisi": len(sent_lens),
        "cumle_siniri": limit,
        "siniri_asan_cumle": over,
        "siniri_asan_cumle_yuzde": _pct(over, len(sent_lens)),
        "en_uzun_cumle": max(sent_lens, default=0),
        "paragraf_sayisi": len(paras),
        "uc_cumleyi_asan_paragraf": sum(1 for n in para_sents if n > 3),
        "ikiden_fazla_vurgulu_paragraf": sum(1 for n in para_bold if n > 2),
        "bolum_sayisi": len(c.bolumler),
        "bolum_siniri": cfg["max_sections"],
        "bolum_siniri_uygun": len(c.bolumler) <= cfg["max_sections"],
        "kisaca_madde": len(c.kisaca),
        "akilda_kalsin_var": bool(c.akilda_kalsin.strip()),
        "sozluk_terim": len(c.sozluk),
        "kaynakli_birim": cited,
        "toplam_birim": len(units),
        "kaynakli_birim_yuzde": _pct(cited, len(units)),
        "gecersiz_kaynak_no": invalid,
        "eksik_bilgi_notu": bool(c.eksik_bilgi.strip()),
    }


def number_grounding(c: BerrakIcerik, sources: list[dict]) -> dict:
    """Çıktıdaki sayılar kaynak metinlerde geçiyor mu? (uydurma sayı kontrolü)

    Not: "3 şey gerekir" gibi tek basamaklı sayılar sayılmaz. Kaynakta farklı yazılmış
    bir sayı (ör. "yüzde kırk" ↔ "%40") eşleşmeyebilir; bu yüzden eşleşmeyenler elle kontrol edilmelidir.
    """
    out_nums = numbers(c.plain_text())
    src_nums = numbers("\n".join(s.get("content", "") for s in sources))
    return {
        "sayi": len(out_nums),
        "kaynakta_gecen": len(out_nums & src_nums),
        "kaynakta_gecmeyen": sorted(out_nums - src_nums),
    }
