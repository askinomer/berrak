"""İnternette Türkçe kaynak arama.

Öncelik: Tavily (ücretsiz plan, ayda 1.000 kredi; basic arama = 1 kredi).
Tavily anahtarı yoksa: DuckDuckGo (anahtar gerektirmez, sadece kısa özetler döner).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

MAX_CHARS_PER_SOURCE = 4000  # LLM'e giden metni sınırlı tutar


@dataclass
class Source:
    title: str
    url: str
    content: str

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "content": self.content}


class SearchError(RuntimeError):
    pass


def _trim(text: str | None, limit: int = MAX_CHARS_PER_SOURCE) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " …"


def tavily_search(query: str, api_key: str, max_results: int = 5) -> list[Source]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    params = dict(
        query=query,
        search_depth="basic",  # 1 kredi; "advanced" 2 kredi harcar
        topic="general",
        max_results=max_results,
        country="turkey",
        language="tr",
        include_raw_content="text",
    )
    try:
        data = client.search(**params, filter_by_language=True)
    except Exception as exc:  # dil filtresi desteklenmezse veya hata verirse
        log.warning("Tavily dil filtresiyle başarısız (%s), filtresiz deneniyor.", exc)
        data = None
    if not data or not data.get("results"):
        # Dil filtresi hiç sonuç bırakmadıysa (nadir konular) filtresiz tekrar dene
        try:
            data = client.search(**params)
        except Exception as exc2:
            raise SearchError(f"Tavily araması başarısız: {exc2}") from exc2

    sources = []
    for r in data.get("results", []):
        body = r.get("raw_content") or r.get("content") or ""
        if len(body) < 80:
            continue
        sources.append(Source(r.get("title") or r.get("url", ""), r.get("url", ""), _trim(body)))
    return sources


def duckduckgo_search(query: str, max_results: int = 6) -> list[Source]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise SearchError("DuckDuckGo için 'ddgs' paketi kurulu değil.") from exc
    try:
        results = DDGS().text(query, region="tr-tr", safesearch="moderate", max_results=max_results)
    except Exception as exc:
        raise SearchError(f"DuckDuckGo araması başarısız: {exc}") from exc
    return [
        Source(r.get("title", ""), r.get("href", ""), _trim(r.get("body", "")))
        for r in results
        if r.get("body")
    ]


def search(queries: list[str], tavily_key: str | None, max_results: int = 5) -> tuple[list[Source], str]:
    """Bir veya birden fazla sorguyu arar, aynı URL'leri tekilleştirir.

    Dönüş: (kaynaklar, kullanılan_motor)
    """
    engine = "Tavily" if tavily_key else "DuckDuckGo"
    seen, merged = set(), []
    errors = []
    for q in queries:
        try:
            batch = tavily_search(q, tavily_key, max_results) if tavily_key else duckduckgo_search(q, max_results)
        except SearchError as exc:
            errors.append(str(exc))
            continue
        for s in batch:
            if s.url and s.url not in seen:
                seen.add(s.url)
                merged.append(s)
    if not merged:
        detail = "; ".join(errors) if errors else "Sonuç bulunamadı."
        raise SearchError(detail)
    return merged[: max_results + 3], engine
