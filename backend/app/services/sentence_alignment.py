"""Read-only sentence alignment for the reviewer; offsets use UTF-16 on all clients."""
import asyncio
import hashlib
import json
import re
from collections import OrderedDict

from pydantic import BaseModel, Field

from app.services.providers.alignment import SentenceLinks


class AlignmentRequest(BaseModel):
    translated_text: str = Field(min_length=1, max_length=50_000)


class AlignedSentence(BaseModel):
    translation_start: int
    translation_end: int
    arabic_start: int
    arabic_end: int


def sentence_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    # Parenthetical notes stay with their sentence. Decimal numbers and initials
    # without a following space do not create a new span.
    for boundary in re.finditer(r"(?<=[.!?؟])\s+|\n+", text):
        end = boundary.start()
        if text[start:end].strip():
            spans.append((start, end))
        start = boundary.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def utf16_offset(text: str, offset: int) -> int:
    return len(text[:offset].encode('utf-16-le')) // 2


def validated_links(arabic: str, translated: str, result: SentenceLinks) -> list[AlignedSentence]:
    sentences = sentence_spans(translated)
    links = []
    seen = set()
    for link in result.links:
        if not 0 <= link.sentence_id < len(sentences) or link.sentence_id in seen:
            continue
        excerpt = link.arabic_excerpt
        if not excerpt.strip() or link.occurrence > 1000:
            continue
        start = -1
        for _ in range(link.occurrence + 1):
            start = arabic.find(excerpt, start + 1)
            if start < 0:
                break
        if start < 0:
            continue
        a, b = sentences[link.sentence_id]
        links.append(AlignedSentence(
            translation_start=utf16_offset(translated, a),
            translation_end=utf16_offset(translated, b),
            arabic_start=utf16_offset(arabic, start),
            arabic_end=utf16_offset(arabic, start + len(excerpt)),
        ))
        seen.add(link.sentence_id)
    return sorted(links, key=lambda link: link.translation_start)


_cache: OrderedDict[str, list[AlignedSentence]] = OrderedDict()
_limit = asyncio.Semaphore(2)


def alignment_input(arabic: str, translated: str, english: str | None = None):
    from app.core.config import get_settings

    settings = get_settings()
    payload = dict(arabic_text=arabic, approved_english=english, sentences=[
        dict(id=i, text=translated[a:b]) for i, (a, b) in enumerate(sentence_spans(translated))
    ])
    if len(payload['sentences']) > 250:
        raise ValueError('This passage is too long for sentence highlighting')
    key = hashlib.sha256(json.dumps(
        [settings.translation_provider, settings.openai_model, payload, translated],
        ensure_ascii=False,
    ).encode()).hexdigest()
    return settings, payload, key


def cached_alignment(arabic: str, translated: str, english: str | None = None):
    """Reuse only an exact draft match; never save locally shifted editor offsets."""
    try:
        _, _, key = alignment_input(arabic, translated, english)
    except ValueError:
        return None
    return _cache.get(key)


async def align_sentences(arabic: str, translated: str, english: str | None = None):
    from app.services.providers.factory import build_provider

    settings, payload, key = alignment_input(arabic, translated, english)
    async with asyncio.timeout(35):
        async with _limit:
            if key in _cache:
                _cache.move_to_end(key)
                return _cache[key]
            provider = build_provider(settings)
            try:
                result = await provider.align_sentences(payload)
            finally:
                if client := getattr(provider, 'client', None):
                    await client.close()
            links = validated_links(arabic, translated, result)
            if links:
                _cache[key] = links
                if len(_cache) > 64:
                    _cache.popitem(last=False)
            return links
