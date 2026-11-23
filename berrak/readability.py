"""Türkçe okunabilirlik araçları.

- Heceleme (Türkçe hece kuralları)
- Ateşman okunabilirlik formülü (1997)
- Cümle / kelime istatistikleri ve uzun cümle tespiti
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VOWELS = set("aeıioöuüâîûAEIİOÖUÜÂÎÛ")
LETTERS = "A-Za-zÇĞİÖŞÜçğıöşüÂÎÛâîû"
WORD_RE = re.compile(rf"[{LETTERS}]+(?:['’][{LETTERS}]+)?")

# Yabancı kökenli kelimelerde hece başında kalabilen ünsüz ikilileri
# (ör. e-lek-trik, kon-trol). Türkçe kökenli kelimelerde bu ikililer
# hece başında bulunmadığı için kural onları etkilemez.
ONSET_CLUSTERS = {
    "tr", "dr", "kr", "gr", "pr", "br", "fr",
    "pl", "bl", "kl", "gl", "fl",
}

# Cümle sonu sanılmaması gereken yaygın kısaltmalar
ABBREVIATIONS = {
    "vb", "vs", "örn", "dr", "prof", "doç", "yrd", "bkz", "sn", "no",
    "s", "yy", "m.ö", "m.s", "çev", "ed", "st", "mr", "mrs",
}


def syllabify(word: str) -> list[str]:
    """Bir kelimeyi Türkçe hece kurallarına göre hecelere ayırır.

    Kural: Her hecede bir ünlü vardır. İki ünlü arasındaki ünsüzlerden
    sonuncusu bir sonraki heceye geçer (ka-lem, Türk-çe, ilk-ba-har).

    >>> syllabify("değerlendirilemeyenlerden")
    ['de', 'ğer', 'len', 'di', 'ri', 'le', 'me', 'yen', 'ler', 'den']
    """
    vowel_idx = [i for i, ch in enumerate(word) if ch in VOWELS]
    if len(vowel_idx) <= 1:
        return [word]

    cuts: list[int] = []
    for a, b in zip(vowel_idx, vowel_idx[1:]):
        consonants = b - a - 1
        if consonants == 0:
            cut = b
        elif consonants >= 3 and word[b - 2 : b].lower() in ONSET_CLUSTERS:
            cut = b - 2
        else:
            cut = b - 1
        cuts.append(cut)

    parts, start = [], 0
    for cut in cuts:
        parts.append(word[start:cut])
        start = cut
    parts.append(word[start:])
    return parts


def count_syllables(word: str) -> int:
    """Türkçede hece sayısı ünlü sayısına eşittir."""
    return max(1, sum(1 for ch in word if ch in VOWELS))


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def split_sentences(text: str) -> list[str]:
    """Metni cümlelere böler. Satır sonları (madde işaretleri) de cümle sayılır."""
    sentences: list[str] = []
    for line in re.split(r"\n+", text):
        line = line.strip(" \t-•*·")
        if not line:
            continue
        buf = ""
        for piece in re.split(r"(?<=[.!?…])\s+", line):
            buf = f"{buf} {piece}".strip() if buf else piece
            last = re.findall(rf"([{LETTERS}.]+)\.$", buf)
            if last and last[0].lower().rstrip(".") in ABBREVIATIONS:
                continue  # kısaltma: cümle bitmedi
            if words(buf):
                sentences.append(buf)
            buf = ""
        if buf and words(buf):
            sentences.append(buf)
    return sentences


def prose_only(text: str, min_words: int = 8) -> str:
    """Web sayfası metninden menü, başlık, buton gibi kısa satırları atar.

    Ölçümün adil olması için sadece düzyazı paragraflar bırakılır: en az
    `min_words` kelimelik ve cümle sonu noktalaması içeren satırlar.
    Geriye 3 cümleden az kalırsa metin olduğu gibi döner.
    """
    keep = [ln.strip() for ln in text.splitlines()
            if len(words(ln)) >= min_words and re.search(r"[.!?…]", ln)]
    cleaned = "\n".join(keep)
    return cleaned if len(split_sentences(cleaned)) >= 3 else text


def atesman_label(score: float) -> str:
    if score >= 90:
        return "Çok kolay"
    if score >= 70:
        return "Kolay"
    if score >= 50:
        return "Orta güçlükte"
    if score >= 30:
        return "Zor"
    return "Çok zor"


@dataclass
class ReadabilityReport:
    words: int = 0
    sentences: int = 0
    syllables: int = 0
    atesman: float = 0.0
    label: str = "-"
    avg_sentence_words: float = 0.0
    avg_word_syllables: float = 0.0
    long_word_ratio: float = 0.0  # 4 ve daha fazla heceli kelimelerin oranı
    long_sentences: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def analyze(text: str, long_sentence_limit: int = 15) -> ReadabilityReport:
    """Ateşman (1997): 198,825 − 40,175 × (hece/kelime) − 2,610 × (kelime/cümle)."""
    ws = words(text)
    sents = split_sentences(text)
    if not ws or not sents:
        return ReadabilityReport()

    syl = [count_syllables(w) for w in ws]
    n_w, n_s, n_syl = len(ws), len(sents), sum(syl)
    x1 = n_syl / n_w
    x2 = n_w / n_s
    score = 198.825 - 40.175 * x1 - 2.610 * x2
    score = max(0.0, min(100.0, score))

    return ReadabilityReport(
        words=n_w,
        sentences=n_s,
        syllables=n_syl,
        atesman=round(score, 1),
        label=atesman_label(score),
        avg_sentence_words=round(x2, 1),
        avg_word_syllables=round(x1, 2),
        long_word_ratio=round(sum(1 for s in syl if s >= 4) / n_w, 3),
        long_sentences=[s for s in sents if len(words(s)) > long_sentence_limit],
    )


def reading_minutes(n_words: int, wpm: int = 120) -> int:
    """Tahmini okuma süresi. Disleksi/DEHB için yavaş bir hız varsayılır."""
    return max(1, round(n_words / wpm))
