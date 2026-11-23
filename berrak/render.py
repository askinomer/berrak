"""Sadeleştirilmiş içeriği okunaklı, tek dosyalık bir HTML sayfasına dönüştürür.

Yazı tipleri sayfanın içine gömülür; sayfa internet olmadan da düzgün görünür
ve indirilip paylaşılabilir.
"""

from __future__ import annotations

import base64
import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .llm import BerrakIcerik
from .readability import WORD_RE, ReadabilityReport, syllabify

FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Tüm yazı tiplerinin Türkçe karakterleri (ğ, ş, ı, İ, ç, ö, ü) desteklediği kontrol edildi.
FONTS = {
    "Lexend": "lexend",
    "Atkinson Hyperlegible": "atkinson-hyperlegible-next",
    "OpenDyslexic": "opendyslexic",
    "Verdana (sistem)": None,
}

# fontsource alt kümeleri: latin (ı, ç, ö, ü dahil) + latin-ext (ğ, ş, İ dahil)
UNICODE_RANGES = {
    "latin": "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,"
             "U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD",
    "latin-ext": "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,"
                 "U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,"
                 "U+2113,U+2C60-2C7F,U+A720-A7FF",
}

# Saf siyah/beyaz yerine yumuşak kontrast (BDA Dyslexia Style Guide önerisi)
THEMES = {
    "Krem":       dict(bg="#FBF5E6", surface="#FFFDF7", text="#2A2A2A", muted="#5E5A50",
                       accent="#1D5C87", soft="#F2E7C9", border="#E3D6B5", hl="#FFE58A", syl="#B4471B"),
    "Açık mavi":  dict(bg="#EAF2F9", surface="#F7FBFE", text="#1E2933", muted="#4F5D6A",
                       accent="#1C5D99", soft="#D6E6F3", border="#C3D6E8", hl="#FFE58A", syl="#A8431D"),
    "Açık yeşil": dict(bg="#EDF5E9", surface="#F9FCF7", text="#22301F", muted="#52604E",
                       accent="#2D6A3E", soft="#DCEBD4", border="#C7DBBD", hl="#FFE58A", syl="#9C3F1A"),
    "Gri-beyaz":  dict(bg="#F4F4F1", surface="#FFFFFF", text="#262626", muted="#5A5A5A",
                       accent="#1F5A8A", soft="#E8E8E3", border="#D9D9D3", hl="#FFE58A", syl="#AD4419"),
    "Koyu":       dict(bg="#1E1F22", surface="#27292D", text="#E9E5DA", muted="#AAA698",
                       accent="#8CC4FF", soft="#33363B", border="#3F434A", hl="#5B4A12", syl="#F2A66B"),
}


@dataclass
class DisplaySettings:
    font: str = "Lexend"
    font_size: int = 19
    line_height: float = 1.8
    letter_spacing: float = 0.03
    word_spacing: float = 0.12
    theme: str = "Krem"
    syllables: bool = False
    syllable_min: int = 3
    focus_mode: bool = False
    reading_ruler: bool = False


@lru_cache(maxsize=8)
def _font_face_css(font: str) -> tuple[str, str]:
    """Seçilen yazı tipi için gömülü @font-face kuralları ve font-family değeri."""
    slug = FONTS.get(font)
    fallback = 'Verdana, "Segoe UI", Arial, sans-serif'
    if not slug:
        return "", fallback
    rules = []
    for subset, urange in UNICODE_RANGES.items():
        for weight in (400, 700):
            path = FONT_DIR / f"{slug}-{subset}-{weight}-normal.woff2"
            if not path.exists():
                continue
            data = base64.b64encode(path.read_bytes()).decode()
            ur = f"unicode-range:{urange};" if (FONT_DIR / f"{slug}-latin-ext-400-normal.woff2").exists() else ""
            rules.append(
                f"@font-face{{font-family:'Berrak {font}';font-style:normal;font-weight:{weight};"
                f"font-display:swap;src:url(data:font/woff2;base64,{data}) format('woff2');{ur}}}"
            )
    return "\n".join(rules), f"'Berrak {font}', {fallback}"


class _Formatter:
    def __init__(self, settings: DisplaySettings, n_sources: int):
        self.s = settings
        self.n_sources = n_sources

    def _syllable_word(self, m: re.Match) -> str:
        word = m.group(0)
        parts = syllabify(word)
        if len(parts) < self.s.syllable_min:
            return html.escape(word)
        spans = "".join(f'<span class="s{i % 2}">{html.escape(p)}</span>' for i, p in enumerate(parts))
        return f'<span class="hw" aria-label="{html.escape(word)}">{spans}</span>'

    def _plain(self, text: str) -> str:
        if not self.s.syllables:
            return html.escape(text)
        out, last = [], 0
        for m in WORD_RE.finditer(text):
            out.append(html.escape(text[last : m.start()]))
            out.append(self._syllable_word(m))
            last = m.end()
        out.append(html.escape(text[last:]))
        return "".join(out)

    def _citations(self, text: str) -> str:
        out, last = [], 0
        for m in re.finditer(r"\s?\[(\d+(?:\s*,\s*\d+)*)\]", text):
            out.append(self._plain(text[last : m.start()]))
            links = []
            for num in re.findall(r"\d+", m.group(1)):
                n = int(num)
                if 1 <= n <= self.n_sources:
                    links.append(f'<a href="#kaynak-{n}" aria-label="Kaynak {n}">{n}</a>')
            if links:
                out.append(f'<sup class="cite">{",".join(links)}</sup>')
            last = m.end()
        out.append(self._plain(text[last:]))
        return "".join(out)

    def __call__(self, text: str) -> str:
        """**kalın** → <strong>, [1] → kaynak bağlantısı, isteğe bağlı heceleme."""
        out = []
        for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text or "")):
            formatted = self._citations(part)
            out.append(f"<strong>{formatted}</strong>" if i % 2 else formatted)
        return "".join(out)


def render_html(
    content: BerrakIcerik,
    sources: list[dict],
    settings: DisplaySettings | None = None,
    report: ReadabilityReport | None = None,
    minutes: int | None = None,
    is_demo: bool = False,
) -> str:
    s = settings or DisplaySettings()
    t = THEMES.get(s.theme, THEMES["Krem"])
    font_css, family = _font_face_css(s.font)
    fmt = _Formatter(s, len(sources))
    esc = html.escape
    total = len(content.bolumler)

    meta = []
    if minutes:
        meta.append(f"<span>Okuma süresi: yaklaşık <b>{minutes} dakika</b></span>")
    if report and report.words:
        meta.append(f"<span>Okunabilirlik: <b>{esc(report.label)}</b> (Ateşman {report.atesman:.0f}/100)</span>")
    meta.append(f"<span>{total} bölüm</span>")

    kisaca = "".join(f"<li>{fmt(k)}</li>" for k in content.kisaca)

    sections = []
    for i, b in enumerate(content.bolumler, 1):
        paras = "".join(f'<p class="read">{fmt(p)}</p>' for p in b.paragraflar)
        items = "".join(f'<li class="read">{fmt(m)}</li>' for m in b.maddeler)
        items = f"<ul class='items'>{items}</ul>" if items else ""
        sections.append(f"""
<section class="card section" id="bolum-{i}" data-index="{i}" aria-labelledby="h-{i}">
  <p class="step">Bölüm {i} / {total}</p>
  <h2 id="h-{i}">{fmt(b.baslik)}</h2>
  <p class="lead read">{fmt(b.ozet)}</p>
  {paras}{items}
  <div class="sec-tools">
    <button type="button" class="btn ghost" data-speak="bolum-{i}">Bu bölümü dinle</button>
    <label class="done"><input type="checkbox" data-done="{i}"> Okudum</label>
  </div>
</section>""")

    glossary = ""
    if content.sozluk:
        rows = "".join(f"<div class='term'><dt>{esc(x.terim)}</dt><dd>{fmt(x.aciklama)}</dd></div>"
                       for x in content.sozluk)
        glossary = f'<section class="card"><h2>Sözlük</h2><dl class="glossary">{rows}</dl></section>'

    remember = ""
    if content.akilda_kalsin:
        remember = (f'<section class="card remember" id="akilda"><h2>Akılda kalsın</h2>'
                    f'<p class="read">{fmt(content.akilda_kalsin)}</p></section>')

    missing = ""
    if content.eksik_bilgi:
        missing = f'<p class="note"><b>Not:</b> {fmt(content.eksik_bilgi)}</p>'

    def _src(i: int, x: dict) -> str:
        label = esc(x.get("title") or x.get("url") or f"Kaynak {i}")
        url = x.get("url") or ""
        if url.startswith(("http://", "https://")):
            label = f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>'
        return f'<li id="kaynak-{i}">{label}</li>'

    src_items = "".join(_src(i, x) for i, x in enumerate(sources, 1))
    demo_badge = '<p class="demo">Demo içeriği: canlı arama yapılmadı.</p>' if is_demo else ""

    pager = ""
    if s.focus_mode and total > 1:
        dots = "".join(f'<button type="button" class="dot" data-go="{i}" aria-label="Bölüm {i}"></button>'
                       for i in range(1, total + 1))
        pager = f"""
<nav class="pager" aria-label="Bölümler arasında geçiş">
  <button type="button" class="btn" id="prev">← Önceki</button>
  <div class="dots">{dots}</div>
  <button type="button" class="btn primary" id="next">Sonraki →</button>
</nav>"""

    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(content.baslik)} · Berrak</title>
<style>
{font_css}
:root {{
  --bg:{t['bg']}; --surface:{t['surface']}; --text:{t['text']}; --muted:{t['muted']};
  --accent:{t['accent']}; --soft:{t['soft']}; --border:{t['border']}; --hl:{t['hl']}; --syl:{t['syl']};
  --fs:{s.font_size}px; --lh:{s.line_height}; --ls:{s.letter_spacing}em; --ws:{s.word_spacing}em;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; background:var(--bg); color:var(--text);
  font-family:{family}; font-size:var(--fs); line-height:var(--lh);
  letter-spacing:var(--ls); word-spacing:var(--ws);
  text-align:left; hyphens:none; -webkit-font-smoothing:antialiased;
}}
.topbar {{
  position:sticky; top:0; z-index:5; background:var(--bg);
  border-bottom:1px solid var(--border);
}}
.topbar-inner {{
  max-width:46rem; margin:0 auto; padding:.55rem 1rem;
  display:flex; gap:.6rem; align-items:center; flex-wrap:wrap;
  font-size:.8em; letter-spacing:0; word-spacing:0;
}}
.brand {{ font-weight:700; color:var(--accent); margin-right:auto; }}
.progress {{ height:5px; background:var(--soft); }}
.progress > div {{ height:100%; width:0; background:var(--accent); transition:width .15s; }}
main {{ max-width:46rem; margin:0 auto; padding:1.5rem 1rem 4rem; }}
h1 {{ font-size:1.65em; line-height:1.3; margin:.4rem 0 .6rem; }}
h2 {{ font-size:1.25em; line-height:1.35; margin:.1rem 0 .7rem; }}
.meta {{ display:flex; flex-wrap:wrap; gap:.4rem 1.2rem; color:var(--muted); font-size:.8em; margin-bottom:1.4rem; }}
p, li {{ margin:0 0 1em; max-width:65ch; }}
strong {{ font-weight:700; color:var(--text); background:linear-gradient(transparent 62%, var(--hl) 62%); }}
.card {{
  background:var(--surface); border:1px solid var(--border); border-radius:14px;
  padding:1.3rem 1.4rem 1rem; margin:0 0 1.3rem;
}}
.summary {{ background:var(--soft); border-color:transparent; }}
.summary h2, .remember h2 {{ font-size:1em; text-transform:none; color:var(--accent); margin-bottom:.5rem; }}
.summary ul {{ margin:0; padding-left:1.2em; }}
.summary li {{ margin-bottom:.5em; }}
.step {{ color:var(--muted); font-size:.75em; margin:0 0 .2rem; letter-spacing:.04em; }}
.lead {{ font-weight:600; }}
.items {{ padding-left:1.2em; }}
.items li {{ margin-bottom:.6em; }}
.items li::marker {{ color:var(--accent); }}
.sec-tools {{
  display:flex; justify-content:space-between; align-items:center; gap:.8rem; flex-wrap:wrap;
  border-top:1px dashed var(--border); padding-top:.8rem; margin-top:.4rem;
  font-size:.8em; letter-spacing:0; word-spacing:0;
}}
.done {{ display:flex; align-items:center; gap:.4rem; cursor:pointer; color:var(--muted); }}
.done input {{ width:1.2em; height:1.2em; accent-color:var(--accent); }}
.section.is-done {{ opacity:.72; }}
.section.is-done .step::after {{ content:"  ·  okundu"; color:var(--accent); }}
.remember {{ border-left:6px solid var(--accent); }}
.remember p {{ font-weight:600; margin:0 0 .4rem; }}
.glossary {{ margin:0; }}
.term {{ padding:.55rem 0; border-bottom:1px solid var(--border); }}
.term:last-child {{ border-bottom:0; }}
dt {{ font-weight:700; }}
dd {{ margin:0; }}
.btn {{
  font:inherit; font-size:1em; letter-spacing:0; padding:.45rem .9rem; border-radius:999px;
  border:1px solid var(--border); background:var(--surface); color:var(--text); cursor:pointer;
}}
.btn:hover {{ border-color:var(--accent); }}
.btn.primary {{ background:var(--accent); color:var(--bg); border-color:var(--accent); }}
.btn.ghost {{ background:transparent; }}
.btn:focus-visible, a:focus-visible, input:focus-visible {{ outline:3px solid var(--accent); outline-offset:2px; }}
select.btn {{ padding-right:.6rem; }}
a {{ color:var(--accent); }}
sup.cite {{ font-size:.62em; letter-spacing:0; margin-left:.1em; }}
sup.cite a {{ text-decoration:none; padding:0 .15em; }}
.sources ol {{ padding-left:1.3em; font-size:.85em; }}
.sources li {{ margin-bottom:.5em; word-break:break-word; }}
.note {{ background:var(--soft); padding:.8rem 1rem; border-radius:10px; font-size:.9em; }}
.demo {{ display:inline-block; background:var(--hl); color:var(--text); padding:.2rem .7rem; border-radius:6px; font-size:.75em; }}
footer {{ color:var(--muted); font-size:.75em; line-height:1.6; margin-top:2rem; }}
.hw .s1 {{ color:var(--syl); }}
.speaking {{ background:var(--hl); border-radius:6px; box-shadow:0 0 0 4px var(--hl); }}
.pager {{
  position:sticky; bottom:0; display:flex; justify-content:space-between; align-items:center;
  gap:.6rem; padding:.7rem 0; background:var(--bg); font-size:.8em; letter-spacing:0;
}}
.dots {{ display:flex; gap:.4rem; flex-wrap:wrap; justify-content:center; }}
.dot {{ width:.8rem; height:.8rem; border-radius:50%; border:2px solid var(--accent); background:transparent; padding:0; cursor:pointer; }}
.dot.on {{ background:var(--accent); }}
.focus .section {{ display:none; }}
.focus .section.active {{ display:block; }}
#ruler {{
  position:fixed; left:0; right:0; height:calc(var(--fs) * var(--lh) * 1.6); pointer-events:none;
  background:var(--hl); opacity:.28; mix-blend-mode:multiply; display:none; z-index:4;
}}
#tts-msg {{ color:var(--muted); }}
@media (max-width:560px) {{ .card {{ padding:1rem; }} h1 {{ font-size:1.4em; }} }}
@media (prefers-reduced-motion:reduce) {{ html {{ scroll-behavior:auto; }} .progress > div {{ transition:none; }} }}
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-inner">
    <span class="brand">Berrak</span>
    <button type="button" class="btn primary" id="speak-all">Tümünü dinle</button>
    <button type="button" class="btn" id="stop">Durdur</button>
    <label>Hız
      <select class="btn" id="rate">
        <option value="0.75">Yavaş</option><option value="0.9" selected>Normal</option><option value="1.1">Hızlı</option>
      </select>
    </label>
    <span id="tts-msg" role="status"></span>
  </div>
  <div class="progress" aria-hidden="true"><div id="bar"></div></div>
</div>
<div id="ruler" aria-hidden="true"></div>
<main class="{'focus' if s.focus_mode and total > 1 else ''}">
  {demo_badge}
  <h1>{esc(content.baslik)}</h1>
  <div class="meta">{''.join(meta)}</div>

  <section class="card summary" id="kisaca">
    <h2>Kısaca</h2>
    <ul>{kisaca}</ul>
  </section>

  {''.join(sections)}
  {pager}
  {remember}
  {glossary}
  {missing}

  <section class="card sources" id="kaynaklar">
    <h2>Kaynaklar</h2>
    <ol>{src_items}</ol>
  </section>

  <footer>
    Bu sayfa, yukarıdaki kaynaklardaki bilgiler yapay zekâ ile sadeleştirilerek hazırlanmıştır.
    Önemli kararlar için kaynakların aslına bakın. Berrak tanı koymaz; yalnızca okumayı kolaylaştırır.
  </footer>
</main>
<script>
(() => {{
  const $ = (q, el = document) => el.querySelector(q);
  const $$ = (q, el = document) => [...el.querySelectorAll(q)];
  const store = {{
    get(k) {{ try {{ return JSON.parse(localStorage.getItem(k)); }} catch (e) {{ return null; }} }},
    set(k, v) {{ try {{ localStorage.setItem(k, JSON.stringify(v)); }} catch (e) {{}} }}
  }};
  const KEY = "berrak:" + {json.dumps(content.baslik[:60]).replace("<", "\\u003c").replace(">", "\\u003e")};

  // İlerleme çubuğu
  const bar = $("#bar");
  const onScroll = () => {{
    const h = document.documentElement;
    const max = h.scrollHeight - h.clientHeight;
    bar.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 100) + "%";
  }};
  addEventListener("scroll", onScroll, {{ passive:true }}); onScroll();

  // "Okudum" işaretleri
  const done = store.get(KEY) || {{}};
  $$("[data-done]").forEach(cb => {{
    const i = cb.dataset.done, sec = $("#bolum-" + i);
    const apply = () => sec.classList.toggle("is-done", cb.checked);
    cb.checked = !!done[i]; apply();
    cb.addEventListener("change", () => {{ done[i] = cb.checked; store.set(KEY, done); apply(); updateDots(); }});
  }});

  // Odak modu: bir seferde tek bölüm
  const focus = $("main.focus");
  const secs = $$(".section");
  let cur = 0;
  function updateDots() {{
    $$(".dot").forEach((d, i) => d.classList.toggle("on", i === cur || !!done[i + 1]));
  }}
  function show(i) {{
    cur = Math.max(0, Math.min(secs.length - 1, i));
    secs.forEach((s, j) => s.classList.toggle("active", j === cur));
    if ($("#prev")) $("#prev").disabled = cur === 0;
    if ($("#next")) $("#next").textContent = cur === secs.length - 1 ? "Bitti ✓" : "Sonraki →";
    updateDots();
  }}
  if (focus) {{
    show(0);
    $("#prev").onclick = () => {{ show(cur - 1); secs[cur].scrollIntoView(); }};
    $("#next").onclick = () => {{
      const cb = $("[data-done='" + (cur + 1) + "']", secs[cur]);
      if (cb && !cb.checked) cb.click();
      if (cur < secs.length - 1) {{ show(cur + 1); secs[cur].scrollIntoView(); }}
      else $("#akilda, #kaynaklar")?.scrollIntoView();
    }};
    $$(".dot").forEach(d => d.onclick = () => {{ show(+d.dataset.go - 1); secs[cur].scrollIntoView(); }});
  }}

  // Okuma cetveli
  const ruler = $("#ruler");
  if ({str(s.reading_ruler).lower()}) {{
    ruler.style.display = "block";
    addEventListener("mousemove", e => {{ ruler.style.top = (e.clientY - ruler.offsetHeight / 2) + "px"; }});
    addEventListener("touchmove", e => {{ ruler.style.top = (e.touches[0].clientY - ruler.offsetHeight / 2) + "px"; }}, {{ passive:true }});
  }}

  // Sesli okuma (tarayıcının Türkçe sesi)
  const synth = window.speechSynthesis;
  const msg = $("#tts-msg");
  let trVoice = null;
  const pickVoice = () => {{
    if (!synth) return;
    const vs = synth.getVoices();
    trVoice = vs.find(v => /^tr/i.test(v.lang)) || null;
  }};
  if (synth) {{ pickVoice(); synth.onvoiceschanged = pickVoice; }}

  const textOf = el => {{
    const c = el.cloneNode(true);
    c.querySelectorAll("sup, .sec-tools, .step").forEach(n => n.remove());
    return c.innerText.replace(/\\s+/g, " ").trim();
  }};
  function speak(blocks) {{
    if (!synth) {{ msg.textContent = "Tarayıcınız sesli okumayı desteklemiyor."; return; }}
    synth.cancel();
    $$(".speaking").forEach(n => n.classList.remove("speaking"));
    if (!trVoice) msg.textContent = "Türkçe ses bulunamadı; varsayılan ses kullanılıyor.";
    else msg.textContent = "";
    const rate = parseFloat($("#rate").value);
    blocks.forEach(el => {{
      const text = textOf(el);
      if (!text) return;
      // Uzun metinler bazı tarayıcılarda kesildiği için cümle cümle okunur
      text.split(/(?<=[.!?…])\\s+/).forEach((part, k, all) => {{
        const u = new SpeechSynthesisUtterance(part);
        u.lang = "tr-TR"; u.rate = rate;
        if (trVoice) u.voice = trVoice;
        if (k === 0) u.onstart = () => {{
          $$(".speaking").forEach(n => n.classList.remove("speaking"));
          el.classList.add("speaking");
          el.scrollIntoView({{ block:"center" }});
        }};
        if (k === all.length - 1) u.onend = () => el.classList.remove("speaking");
        synth.speak(u);
      }});
    }});
  }}
  const readable = root => $$("h1, h2, .read, .summary li", root);
  $("#speak-all").onclick = () => {{
    const visible = focus ? [$("h1"), ...$$("#kisaca li"), ...readable(secs[cur])] : readable(document);
    speak(visible.filter(Boolean));
  }};
  $$("[data-speak]").forEach(b => b.onclick = () => speak(readable($("#" + b.dataset.speak))));
  $("#stop").onclick = () => {{ synth && synth.cancel(); $$(".speaking").forEach(n => n.classList.remove("speaking")); }};
}})();
</script>
</body>
</html>"""
