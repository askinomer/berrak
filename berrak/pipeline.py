"""Arama → sadeleştirme → ölçüm akışı (arayüzden bağımsız)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm import BerrakIcerik, GeminiClient
from .readability import ReadabilityReport, analyze, prose_only, reading_minutes
from .search import search

MAX_PASTED_CHARS = 15000


@dataclass
class Result:
    content: BerrakIcerik
    sources: list[dict]
    before: ReadabilityReport
    after: ReadabilityReport
    minutes: int
    engine: str = ""
    model: str = ""
    queries: list[str] = field(default_factory=list)
    is_demo: bool = False


def _finish(content, sources, original_text, **kw) -> Result:
    after = analyze(content.plain_text())
    return Result(
        content=content,
        sources=sources,
        before=analyze(prose_only(original_text)),
        after=after,
        minutes=reading_minutes(after.words),
        **kw,
    )


def run_topic(
    topic: str,
    level: str,
    gemini_key: str,
    tavily_key: str | None = None,
    deep: bool = False,
    models: list[str] | None = None,
    llm: GeminiClient | None = None,
    on_step=lambda msg: None,
) -> Result:
    llm = llm or GeminiClient(gemini_key, models)

    queries = [topic]
    if deep:
        on_step("Arama sorguları planlanıyor…")
        planned = llm.plan_queries(topic, n=3)
        # "Fotosentez nedir?" ile "fotosentez nedir" aynı sorgu sayılır; boşuna kredi harcanmaz
        seen, queries = set(), []
        for q in [topic, *planned]:
            key = re.sub(r"[^\w\s]", "", q.casefold()).strip()
            if key and key not in seen:
                seen.add(key)
                queries.append(q)
        queries = queries[:3]

    on_step(f"İnternette aranıyor: {', '.join(queries)}")
    found, engine = search(queries, tavily_key, max_results=5)
    sources = [s.as_dict() for s in found]

    on_step(f"{len(sources)} kaynak bulundu. Metin sadeleştiriliyor…")
    return run_sources(sources, level, gemini_key, topic, engine=engine, queries=queries, llm=llm)


def run_sources(
    sources: list[dict],
    level: str,
    gemini_key: str,
    topic: str,
    engine: str = "",
    queries: list[str] | None = None,
    models: list[str] | None = None,
    llm: GeminiClient | None = None,
) -> Result:
    """Önceden bulunmuş kaynakları sadeleştirir. Aynı kaynakları farklı seviyelerde
    karşılaştırmak için de kullanılır (yeni arama yapılmaz, kredi harcanmaz)."""
    llm = llm or GeminiClient(gemini_key, models)
    content = llm.simplify(sources, level, topic=topic)
    original = "\n".join(s["content"] for s in sources)
    return _finish(content, sources, original, engine=engine, model=llm.last_model or "",
                   queries=list(queries or [topic]))


def run_text(
    text: str,
    level: str,
    gemini_key: str,
    title: str = "Yapıştırılan metin",
    models: list[str] | None = None,
    llm: GeminiClient | None = None,
    on_step=lambda msg: None,
) -> Result:
    llm = llm or GeminiClient(gemini_key, models)
    text = text.strip()[:MAX_PASTED_CHARS]
    sources = [{"title": title, "url": "", "content": text}]
    on_step("Metin sadeleştiriliyor…")
    content = llm.simplify(sources, level, topic=None)
    return _finish(content, sources, text, engine="—", model=llm.last_model or "")
