"""Berrak — Streamlit arayüzü.

Çalıştırmak için:  streamlit run app.py
"""

from __future__ import annotations

import os
import re

import streamlit as st

from berrak.demo import demo_result
from berrak.llm import DEFAULT_MODELS, LLMError
from berrak.pipeline import Result, run_text, run_topic
from berrak.prompts import LEVELS
from berrak.readability import analyze
from berrak.render import FONTS, THEMES, DisplaySettings, render_html
from berrak.search import SearchError

st.set_page_config(page_title="Berrak · Kolay okuma asistanı", page_icon="📖", layout="wide")

EXAMPLES = ["Fotosentez nedir?", "Deprem neden olur?", "Yapay zekâ nedir?", "Kurtuluş Savaşı"]


def secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:  # secrets.toml yoksa
        value = ""
    return value or os.environ.get(name, "")


# ---------- Önbellek: aynı konuyu tekrar aramak kredi harcamasın ----------
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False, max_entries=50)
def cached_topic(topic, level, gemini_key, tavily_key, deep, models) -> Result:
    return run_topic(topic, level, gemini_key, tavily_key or None, deep, list(models))


@st.cache_data(ttl=60 * 60 * 24, show_spinner=False, max_entries=50)
def cached_text(text, level, gemini_key, models) -> Result:
    return run_text(text, level, gemini_key, models=list(models))


# ---------- Kenar çubuğu ----------
with st.sidebar:
    st.header("Ayarlar")

    # Kayıtlı anahtarlar (secrets.toml / ortam değişkeni) sunucuda kalır, tarayıcıya hiç gönderilmez.
    # Uygulama internette yayınlansa bile ziyaretçiler anahtarı göremez.
    server_gemini, server_tavily = secret("GEMINI_API_KEY"), secret("TAVILY_API_KEY")
    with st.expander("API anahtarları", expanded=not server_gemini):
        if server_gemini:
            st.caption("Kayıtlı anahtarlar kullanılıyor. İstersen aşağıya kendi anahtarını yazabilirsin.")
        gemini_input = st.text_input("Gemini API anahtarı", type="password",
                                     placeholder="Kayıtlı anahtar kullanılıyor" if server_gemini else "AIza…",
                                     help="Ücretsiz: https://aistudio.google.com/apikey")
        tavily_input = st.text_input("Tavily API anahtarı (isteğe bağlı)", type="password",
                                     placeholder="Kayıtlı anahtar kullanılıyor" if server_tavily else "tvly-…",
                                     help="Ücretsiz plan, ayda 1.000 arama: https://app.tavily.com  "
                                          "Boş bırakılırsa DuckDuckGo kullanılır.")
    gemini_key = gemini_input.strip() or server_gemini
    tavily_key = tavily_input.strip() or server_tavily
    with st.expander("Gelişmiş"):
        model_text = st.text_input("Model sırası", value=", ".join(DEFAULT_MODELS),
                                   help="İlk model kota hatası verirse sıradakine geçilir.")
        models = tuple(m.strip() for m in model_text.split(",") if m.strip()) or tuple(DEFAULT_MODELS)

    st.subheader("Okuyucu")
    level = st.radio("Okuma seviyesi", list(LEVELS), index=1, horizontal=False)

    st.subheader("Görünüm")
    font = st.selectbox("Yazı tipi", list(FONTS), index=0)
    theme = st.selectbox("Arka plan", list(THEMES), index=0)
    font_size = st.slider("Yazı boyutu", 15, 28, 19)
    line_height = st.slider("Satır aralığı", 1.4, 2.4, 1.8, 0.1)
    letter_spacing = st.slider("Harf aralığı", 0.0, 0.12, 0.03, 0.01)
    syllables = st.toggle("Hecelere ayır", help="Uzun kelimelerin hecelerini iki renkle gösterir.")
    syllable_min = st.slider("En az kaç heceli kelimeler", 2, 5, 3, disabled=not syllables)
    focus_mode = st.toggle("Odak modu", help="Bölümleri tek tek gösterir. DEHB için önerilir.")
    reading_ruler = st.toggle("Okuma cetveli", help="Fareyi takip eden bir şerit, okunan satırı belirginleştirir.")

    st.subheader("Arama")
    deep = st.toggle("Kapsamlı arama", help="Konuyu 3 ayrı sorguyla arar. Tavily'de 3 kredi harcar.")

settings = DisplaySettings(
    font=font, font_size=font_size, line_height=line_height, letter_spacing=letter_spacing,
    theme=theme, syllables=syllables, syllable_min=syllable_min,
    focus_mode=focus_mode, reading_ruler=reading_ruler,
)

# ---------- Ana alan ----------
st.title("Berrak")
st.caption("Disleksi ve DEHB için Türkçe okuma asistanı. Bir konu yaz, Berrak araştırsın ve sade bir dille anlatsın.")


def run_safely(fn):
    try:
        with st.status("Hazırlanıyor…", expanded=False) as status:
            result = fn()
            status.update(label="Hazır", state="complete")
        st.session_state.result = result
    except SearchError as exc:
        st.error(f"Arama yapılamadı. İnternet bağlantını ve Tavily anahtarını kontrol et.\n\n{exc}")
    except LLMError as exc:
        msg = str(exc)
        if re.search(r"429|quota|RESOURCE_EXHAUSTED", msg, re.I):
            st.error("Gemini ücretsiz kotası doldu. Bir dakika bekleyip tekrar dene veya başka bir model ekle.")
        elif re.search(r"API key|401|403|PERMISSION", msg, re.I):
            st.error("Gemini API anahtarı geçersiz görünüyor. Kenar çubuğundan kontrol et.")
        else:
            st.error(f"Yapay zekâ yanıtı alınamadı.\n\n{msg}")


tab_topic, tab_text = st.tabs(["Konu ara", "Kendi metnini sadeleştir"])

with tab_topic:
    pick = st.pills("Örnek konular", EXAMPLES, label_visibility="collapsed")
    with st.form("topic_form", border=False):
        topic = st.text_input("Ne öğrenmek istiyorsun?", value=pick or "",
                              placeholder="Örneğin: Deprem neden olur?")
        go = st.form_submit_button("Berraklaştır", type="primary", disabled=not gemini_key)
    if go and topic.strip():
        run_safely(lambda: cached_topic(topic.strip(), level, gemini_key, tavily_key, deep, models))

with tab_text:
    with st.form("text_form", border=False):
        pasted = st.text_area("Sadeleştirmek istediğin metni yapıştır", height=200,
                              placeholder="Ders kitabından, haberden veya bir web sayfasından bir metin…")
        go_text = st.form_submit_button("Sadeleştir", type="primary", disabled=not gemini_key)
    if go_text and pasted.strip():
        run_safely(lambda: cached_text(pasted.strip(), level, gemini_key, models))

if not gemini_key:
    st.info("Başlamak için kenar çubuğuna ücretsiz bir Gemini API anahtarı gir. "
            "Anahtarın yoksa önce hazır örneğe bakabilirsin.")
    if st.button("Demo içeriğini göster"):
        st.session_state.result = demo_result()

# ---------- Sonuç ----------
result: Result | None = st.session_state.get("result")
if result:
    st.divider()
    b, a = result.before, result.after
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Okunabilirlik (Ateşman)", f"{a.atesman:.0f}/100", delta=f"{a.atesman - b.atesman:+.0f} puan",
              help="0-29 çok zor · 30-49 zor · 50-69 orta · 70-89 kolay · 90-100 çok kolay")
    c2.metric("Zorluk", a.label, delta=f"önce: {b.label}", delta_color="off", delta_arrow="off")
    c3.metric("Ortalama cümle", f"{a.avg_sentence_words:.1f} kelime",
              delta=f"önce: {b.avg_sentence_words:.1f} kelime", delta_color="off", delta_arrow="off")
    c4.metric("Okuma süresi", f"~{result.minutes} dk")

    # Tüm model çıktısı render_html içinde HTML'den kaçırılır; sayfaya ham LLM HTML'i girmez.
    page = render_html(result.content, result.sources, settings, a, result.minutes, result.is_demo)
    st.iframe(page, height=900)

    ascii_title = (result.content.baslik.lower().replace("̇", "")
                   .translate(str.maketrans("çğıöşüâîû", "cgiosuaiu")))
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-") or "berrak"
    st.download_button("Sayfayı indir (HTML)", page, file_name=f"berrak-{slug}.html", mime="text/html")

    with st.expander("Kalite raporu"):
        st.write(f"**Arama motoru:** {result.engine}  ·  **Model:** {result.model or '—'}")
        if result.queries:
            st.write("**Sorgular:** " + ", ".join(result.queries))
        st.write(f"**Kelime / cümle:** {a.words} / {a.sentences}  ·  "
                 f"**Uzun kelime oranı (4+ hece):** %{a.long_word_ratio * 100:.0f} "
                 f"(önce %{b.long_word_ratio * 100:.0f})")
        limit = LEVELS[level]["max_words"]
        long_ones = analyze(result.content.plain_text(), long_sentence_limit=limit).long_sentences
        if long_ones:
            st.warning(f"{limit} kelimeden uzun {len(long_ones)} cümle var:")
            for s in long_ones:
                st.markdown(f"- {s}")
        else:
            st.success(f"Tüm cümleler {limit} kelime sınırının altında.")

    with st.expander("Kaynak metinler"):
        for i, s in enumerate(result.sources, 1):
            st.markdown(f"**[{i}] {s['title']}**  \n{s.get('url', '')}")
            st.caption(s["content"][:1200] + ("…" if len(s["content"]) > 1200 else ""))

st.caption("Berrak tanı koymaz; yalnızca okumayı kolaylaştırır. Yapay zekâ hata yapabilir, kaynakları kontrol et.")
