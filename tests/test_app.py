import json

from streamlit.testing.v1 import AppTest

from berrak.demo import demo_result


def _app():
    return AppTest.from_file("../app.py", default_timeout=60)


def test_server_key_never_reaches_browser():
    at = _app()
    at.secrets["GEMINI_API_KEY"] = "AIza-gizli-sunucu-anahtari"
    at.run()
    assert not at.exception
    gemini = next(t for t in at.text_input if t.label == "Gemini API anahtarı")
    assert gemini.value == ""
    assert "AIza-gizli-sunucu-anahtari" not in str(at._tree)
    # Anahtar sunucuda olduğu için "anahtar gir" uyarısı çıkmamalı
    assert not any("API anahtarı gir" in i.value for i in at.info)


def test_demo_flow_without_keys():
    at = _app()
    at.run()
    assert any("API anahtarı gir" in i.value for i in at.info)
    next(b for b in at.button if b.label == "Demo içeriğini göster").click().run()
    assert not at.exception
    assert len(at.metric) == 4
    assert at.metric[0].label == "Okunabilirlik (Ateşman)"


def test_canli_test_script(monkeypatch, tmp_path):
    import canli_test

    monkeypatch.setattr(canli_test, "OUT", tmp_path)
    monkeypatch.setattr(canli_test, "BEKLEME_SN", 0)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-gizli")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    def fake_topic(topic, level, key, tavily_key, deep=False):
        if topic == "Kurtuluş Savaşı":
            raise RuntimeError("429 RESOURCE_EXHAUSTED key=AIza-gizli")
        return demo_result()

    level_calls = []

    def fake_sources(sources, level, key, topic, **kw):
        level_calls.append((level, len(sources)))
        return demo_result()

    monkeypatch.setattr(canli_test, "run_topic", fake_topic)
    monkeypatch.setattr(canli_test, "run_text", lambda text, level, key, title="": demo_result())
    monkeypatch.setattr(canli_test, "run_sources", fake_sources)
    canli_test.main()

    out = next(tmp_path.glob("*-sonuclar.json"))
    raw = out.read_text(encoding="utf-8")
    data = json.loads(raw)
    # 5 konu + 1 metin + seviye deneyi (Fotosentez'in kaynakları 2 seviyede daha)
    assert data["toplam"] == 8 and data["basarili"] == 7
    assert sorted(lv for lv, _ in level_calls) == ["Lise / Yetişkin", "Ortaokul"]
    assert "AIza-gizli" not in raw
    assert len(list(tmp_path.glob("*.html"))) == 7
    assert data["ortalama"]["atesman_sonra"] > data["ortalama"]["atesman_once"]
    assert data["toplamlar"]["gecersiz_kaynak_no"] == 0
    assert "kurallar" in data["calismalar"][0] and "sayilar" in data["calismalar"][0]
    assert next(tmp_path.glob("*-sonuclar.zip")).stat().st_size > 0
