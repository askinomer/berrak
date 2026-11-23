import json
from types import SimpleNamespace

import pytest

from berrak import pipeline, search as search_mod
from berrak.demo import DEMO_CONTENT, DEMO_ORIGINAL, demo_result
from berrak.llm import BerrakIcerik, GeminiClient, LLMError, parse_json
from berrak.readability import analyze, count_syllables, split_sentences, syllabify
from berrak.render import DisplaySettings, render_html


# ---------- Okunabilirlik ----------
@pytest.mark.parametrize("word,expected", [
    ("kalem", "ka-lem"),
    ("Türkçe", "Türk-çe"),
    ("ilkbahar", "ilk-ba-har"),
    ("saat", "sa-at"),
    ("çiftçi", "çift-çi"),
    ("elektrik", "e-lek-trik"),
    ("kontrol", "kon-trol"),
    ("İstanbul", "İs-tan-bul"),
    ("değerlendirilemeyenlerden", "de-ğer-len-di-ri-le-me-yen-ler-den"),
])
def test_syllabify(word, expected):
    assert "-".join(syllabify(word)) == expected


def test_count_syllables():
    assert count_syllables("ışık") == 2
    assert count_syllables("Ağaç") == 2


def test_sentences_keep_abbreviations():
    s = split_sentences("Elma, armut vb. meyveler yararlıdır. Su için!\n- Madde bir\n- Madde iki")
    assert s == ["Elma, armut vb. meyveler yararlıdır.", "Su için!", "Madde bir", "Madde iki"]


def test_atesman_simple_text_is_easier():
    easy = analyze("Kedi uyur. Köpek koşar. Kuş uçar.")
    hard = analyze(DEMO_ORIGINAL)
    assert easy.atesman > 80
    assert hard.atesman < 30
    assert hard.long_sentences


# ---------- Model çıktısı ----------
def test_parse_json_with_code_fence():
    assert parse_json('İşte:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_rejects_garbage():
    with pytest.raises(LLMError):
        parse_json("üzgünüm")


def test_plain_text_strips_markup():
    text = DEMO_CONTENT.plain_text()
    assert "**" not in text and "[1]" not in text


class FakeModels:
    def __init__(self, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        if self.fail_first and len(self.calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        if "arama sorgusu" in contents:
            return SimpleNamespace(text='{"sorgular": ["deprem nedir", "fay hattı"]}')
        return SimpleNamespace(text=json.dumps(DEMO_CONTENT.model_dump(), ensure_ascii=False))


def make_client(fail_first=False):
    c = GeminiClient.__new__(GeminiClient)
    c.client = SimpleNamespace(models=FakeModels(fail_first))
    c.models = ["model-a", "model-b"]
    c.last_model = None
    return c


def test_model_fallback_on_quota_error():
    c = make_client(fail_first=True)
    out = c.simplify([{"title": "t", "url": "u", "content": "metin"}], "Ortaokul", topic="x")
    assert isinstance(out, BerrakIcerik)
    assert c.client.models.calls == ["model-a", "model-b"]
    assert c.last_model == "model-b"


def test_pipeline_topic(monkeypatch):
    def fake_search(queries, key, max_results):
        return [search_mod.Source("Kaynak", "https://ornek.org", DEMO_ORIGINAL)], "Sahte"

    monkeypatch.setattr(pipeline, "search", fake_search)
    r = pipeline.run_topic("Deprem", "Ortaokul", "anahtar", deep=True, llm=make_client())
    assert r.queries[0] == "Deprem" and len(r.queries) == 3
    assert r.after.atesman > r.before.atesman
    assert r.engine == "Sahte"


def test_search_dedupes_urls(monkeypatch):
    src = search_mod.Source("A", "https://a.org", "x" * 100)
    monkeypatch.setattr(search_mod, "duckduckgo_search", lambda q, n: [src])
    found, engine = search_mod.search(["q1", "q2"], None)
    assert engine == "DuckDuckGo" and len(found) == 1


def test_search_raises_when_empty(monkeypatch):
    monkeypatch.setattr(search_mod, "duckduckgo_search", lambda q, n: [])
    with pytest.raises(search_mod.SearchError):
        search_mod.search(["q"], None)


def test_deep_search_skips_duplicate_queries(monkeypatch):
    client = make_client()
    client.plan_queries = lambda topic, n=3: ["fotosentez nedir", "klorofil görevi"]
    calls = []

    def fake_search(queries, key, max_results):
        calls.append(list(queries))
        return [search_mod.Source("Kaynak", "https://ornek.org", DEMO_ORIGINAL)], "Sahte"

    monkeypatch.setattr(pipeline, "search", fake_search)
    r = pipeline.run_topic("Fotosentez nedir?", "Ortaokul", "anahtar", deep=True, llm=client)
    assert r.queries == ["Fotosentez nedir?", "klorofil görevi"]


# ---------- Gerçek SDK'lar, ağa çıkmadan (HTTP katmanı sahte) ----------
def test_gemini_request_through_real_sdk(monkeypatch):
    """google-genai SDK'sı şemamızı gerçekten isteğe çevirebiliyor mu?

    google-genai 2.x istekleri httpx ile, 3.x ise kuruluysa httpx2 ile gönderir;
    ikisinin de istemcisi sahte sunucuya bağlanır.
    """
    import importlib

    sent = []
    text = json.dumps(DEMO_CONTENT.model_dump(), ensure_ascii=False)
    body = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}]}

    for name in ("httpx", "httpx2"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue

        def fake_send(self, request, _mod=mod, **kw):
            sent.append((str(request.url), json.loads(request.content)))
            return _mod.Response(200, json=body, request=request)

        monkeypatch.setattr(mod.Client, "send", fake_send)

    client = GeminiClient("sahte-anahtar", models=["gemini-3.5-flash"])
    out = client.simplify([{"title": "t", "url": "https://a.org", "content": DEMO_ORIGINAL}], "İlkokul", topic="x")
    assert out.baslik == DEMO_CONTENT.baslik
    url, body = sent[0]
    assert "models/gemini-3.5-flash:generateContent" in url
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert "responseSchema" in body["generationConfig"] or "responseJsonSchema" in body["generationConfig"]
    assert "en fazla 8 kelime" in json.dumps(body["systemInstruction"], ensure_ascii=False)


def test_tavily_request_params(monkeypatch):
    """Tavily'ye giden parametreler güncel API dokümanıyla uyumlu mu?"""
    import requests

    sent = []

    def fake_request(self, method, url, **kw):
        data = kw.get("data") or kw.get("json")
        sent.append(json.loads(data) if isinstance(data, str) else data)
        r = requests.models.Response()
        r.status_code, r.url = 200, url
        r._content = json.dumps({"results": [{"title": "T", "url": "https://a.org", "raw_content": "x" * 200}]}).encode()
        r.headers["Content-Type"] = "application/json"
        return r

    monkeypatch.setattr(requests.sessions.Session, "request", fake_request)
    found = search_mod.tavily_search("deprem", "tvly-sahte")
    assert found and found[0].url == "https://a.org"
    p = sent[0]
    assert p["search_depth"] == "basic" and p["country"] == "turkey"
    assert p["language"] == "tr" and p["filter_by_language"] is True
    assert p["include_raw_content"] == "text"


def test_tavily_retries_without_language_filter_when_empty(monkeypatch):
    import requests

    sent = []

    def fake_request(self, method, url, **kw):
        body = json.loads(kw.get("data")) if isinstance(kw.get("data"), str) else kw.get("json")
        sent.append(body)
        results = [] if body.get("filter_by_language") else [
            {"title": "T", "url": "https://a.org", "raw_content": "y" * 200}]
        r = requests.models.Response()
        r.status_code, r.url = 200, url
        r._content = json.dumps({"results": results}).encode()
        r.headers["Content-Type"] = "application/json"
        return r

    monkeypatch.setattr(requests.sessions.Session, "request", fake_request)
    found = search_mod.tavily_search("çok nadir konu", "tvly-sahte")
    assert len(sent) == 2
    assert sent[0]["filter_by_language"] is True and "filter_by_language" not in sent[1]
    assert found and found[0].url == "https://a.org"


# ---------- HTML ----------
def test_render_escapes_model_output():
    evil = DEMO_CONTENT.model_copy(deep=True)
    evil.baslik = "<script>alert(1)</script>"
    evil.bolumler[0].paragraflar = ['<img src=x onerror=alert(1)> **kalın** [1] [9]']
    page = render_html(evil, [{"title": "K", "url": "javascript:alert(1)", "content": ""}])
    assert "<script>alert(1)" not in page
    assert "<img src=x" not in page
    assert "<strong>kalın</strong>" in page
    assert 'href="#kaynak-1"' in page and 'href="#kaynak-9"' not in page
    assert 'href="javascript:' not in page


def test_render_syllables_and_fonts():
    r = demo_result()
    page = render_html(r.content, r.sources, DisplaySettings(syllables=True, font="Lexend"))
    assert 'class="hw"' in page
    assert "font/woff2;base64" in page
    plain = render_html(r.content, r.sources, DisplaySettings(font="Verdana (sistem)"))
    assert "base64" not in plain



# ---------- Değerlendirme ölçümleri ----------
def test_rule_compliance_on_demo():
    from berrak.evaluation import rule_compliance

    k = rule_compliance(DEMO_CONTENT, "Ortaokul", n_sources=1)
    assert k["siniri_asan_cumle"] == 0 and k["gecersiz_kaynak_no"] == 0
    assert k["kisaca_madde"] == 3 and k["bolum_siniri_uygun"] and k["akilda_kalsin_var"]
    assert 0 < k["kaynakli_birim_yuzde"] <= 100


def test_invalid_citation_is_counted():
    from berrak.evaluation import rule_compliance

    c = DEMO_CONTENT.model_copy(deep=True)
    c.bolumler[0].paragraflar = ["Bir bilgi. [1, 4]"]
    assert rule_compliance(c, "Ortaokul", n_sources=2)["gecersiz_kaynak_no"] == 1


def test_number_grounding():
    from berrak.evaluation import number_grounding

    c = DEMO_CONTENT.model_copy(deep=True)
    c.bolumler[0].paragraflar = ["Bu olay 1923 yılında oldu. Oran %45 idi. [1]"]
    g = number_grounding(c, [{"content": "1923 yılında ilan edildi."}])
    assert g["sayi"] == 2 and g["kaynakta_gecen"] == 1 and g["kaynakta_gecmeyen"] == ["45"]


def test_prose_only_drops_menus():
    from berrak.readability import prose_only

    page = "Ana Sayfa\nGiriş Yap\nKategoriler\n" + DEMO_ORIGINAL + "\nPaylaş\nYorum yaz"
    assert prose_only(page).strip() == DEMO_ORIGINAL


def test_run_sources_reuses_sources_without_search(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("arama yapılmamalı")

    monkeypatch.setattr(pipeline, "search", boom)
    src = [{"title": "K", "url": "https://a.org", "content": DEMO_ORIGINAL}]
    r = pipeline.run_sources(src, "İlkokul", "anahtar", "Fotosentez", engine="Tavily", llm=make_client())
    assert r.sources == src and r.engine == "Tavily" and r.queries == ["Fotosentez"]
