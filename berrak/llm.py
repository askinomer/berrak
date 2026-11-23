"""Gemini (ücretsiz katman) ile sadeleştirme.

Çıktı serbest HTML değil, yapılandırılmış JSON'dur. HTML'i biz üretiriz (render.py).
Böylece görünüm her seferinde tutarlı olur ve kullanıcı ayarları sonradan değiştirilebilir.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel, Field, ValidationError

from . import prompts

log = logging.getLogger(__name__)

# Ücretsiz katmanda metin üreten kararlı (stable) modeller, Kasım 2026 itibarıyla.
# Biri kota/erişim hatası verirse sıradakine geçilir. Her modelin kotası ayrıdır.
# Güncel liste: https://ai.google.dev/gemini-api/docs/pricing
DEFAULT_MODELS = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]


class Bolum(BaseModel):
    baslik: str
    ozet: str = Field(description="Bölümü tanıtan tek cümle")
    paragraflar: list[str] = Field(default_factory=list)
    maddeler: list[str] = Field(default_factory=list)


class Terim(BaseModel):
    terim: str
    aciklama: str


class BerrakIcerik(BaseModel):
    baslik: str
    kisaca: list[str] = Field(description="Konunun 3 maddelik özeti")
    bolumler: list[Bolum]
    sozluk: list[Terim] = Field(default_factory=list)
    akilda_kalsin: str = ""
    eksik_bilgi: str = ""

    def plain_text(self) -> str:
        """Okunabilirlik ölçümü için düz metin."""
        parts = [*self.kisaca]
        for b in self.bolumler:
            parts += [b.ozet, *b.paragraflar, *b.maddeler]
        parts.append(self.akilda_kalsin)
        text = "\n".join(p for p in parts if p)
        return re.sub(r"\*\*|\[\d+(?:,\s*\d+)*\]", "", text)


class SorguPlani(BaseModel):
    sorgular: list[str]


class LLMError(RuntimeError):
    pass


def parse_json(text: str) -> dict:
    """Model bazen JSON'u ```json bloğu içinde döndürür; onu da kabul eder."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Model geçerli bir JSON döndürmedi.")
    return json.loads(text[start : end + 1])


class GeminiClient:
    def __init__(self, api_key: str, models: list[str] | None = None):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.models = models or DEFAULT_MODELS
        self.last_model: str | None = None

    def _generate(self, system: str, user: str, schema: type[BaseModel], temperature: float) -> dict:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )
        errors = []
        for model in self.models:
            try:
                resp = self.client.models.generate_content(model=model, contents=user, config=config)
                self.last_model = model
                return parse_json(resp.text or "")
            except LLMError:
                raise
            except Exception as exc:  # kota (429), model yok (404) vb.
                log.warning("%s başarısız: %s", model, exc)
                errors.append(f"{model}: {exc}")
        raise LLMError("Hiçbir model yanıt vermedi.\n" + "\n".join(errors))

    def plan_queries(self, topic: str, n: int = 3) -> list[str]:
        data = self._generate(
            "Sen bir arama asistanısın. Sadece JSON döndür.",
            prompts.QUERY_PLANNER_PROMPT.format(topic=topic, n=n),
            SorguPlani,
            temperature=0.3,
        )
        queries = [q.strip() for q in SorguPlani.model_validate(data).sorgular if q.strip()]
        return queries[:n] or [topic]

    def simplify(self, sources: list[dict], level: str, topic: str | None = None) -> BerrakIcerik:
        system = prompts.build_system_prompt(level)
        src = prompts.format_sources(sources)
        user = (
            prompts.USER_PROMPT_TOPIC.format(topic=topic, sources=src)
            if topic
            else prompts.USER_PROMPT_TEXT.format(sources=src)
        )
        data = self._generate(system, user, BerrakIcerik, temperature=0.4)
        try:
            return BerrakIcerik.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f"Model çıktısı beklenen yapıda değil: {exc}") from exc
