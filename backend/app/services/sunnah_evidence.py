"""Confirm model-proposed hadith wording against a real Sunnah.com page."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.services.canonical_sources import arabic_passage_is_contained
from app.services.retrieval import RetrievedSource

MAX_PAGE_BYTES = 2 * 1024 * 1024


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def page_supports_source(page: str, source: RetrievedSource) -> bool:
    parser = _VisibleText()
    parser.feed(page)
    text = " ".join(parser.parts)
    if not source.arabic_text or not arabic_passage_is_contained(text, source.arabic_text):
        return False
    # Whitespace, markup and typographic punctuation do not change the English wording.
    def words(value: str) -> str:
        return " ".join(re.findall(r"\w+", value.casefold()))
    english = words(source.text)
    return bool(english) and f" {english} " in f" {words(text)} "


async def verify_sunnah_source(
    source: RetrievedSource, client: httpx.AsyncClient
) -> str | None:
    """Return a review issue on unavailable/mismatching evidence; never trust a guess."""
    url = source.url or ""
    try:
        for _ in range(4):
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in {"sunnah.com", "www.sunnah.com"}:
                return "the evidence link left Sunnah.com"
            async with client.stream("GET", url, follow_redirects=False, timeout=20) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_PAGE_BYTES:
                        return "the evidence page exceeded the verification size limit"
                page = content.decode(response.encoding or "utf-8", errors="replace")
                if not page_supports_source(page, source):
                    return "the referenced page did not confirm both Arabic and English wording"
                return None
        return "the evidence page redirected too many times"
    except httpx.HTTPError:
        return "the referenced Sunnah.com page was unavailable for independent verification"
