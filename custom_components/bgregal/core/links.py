"""Text hinter Links zu Errata, FAQ und Almanachen für Regelfragen.

Webseiten werden zu reinem Text, PDFs per pypdf ausgelesen. Der Text liegt 7 Tage im Zwischenspeicher
(<Anleitungen>/<bgg_id>/.links/<hash>.txt); schlägt ein Abruf fehl, gilt der letzte Stand.
"""
from __future__ import annotations

import hashlib
import re
import time
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import aiohttp

MAX_BYTES = 20 * 1024 * 1024
MAX_CHARS = 200_000  # so viel Text je Link geht an das LLM
CACHE_SECONDS = 7 * 24 * 3600
TIMEOUT = aiohttp.ClientTimeout(total=30)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BGRegal; Home Assistant)"}

_SKIP = {"script", "style", "noscript", "template", "svg", "head", "nav", "footer"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
          "table", "ul", "ol", "dd", "dt", "blockquote", "pre", "hr"}


class LinkError(Exception):
    """Abruf fehlgeschlagen und kein gespeicherter Text vorhanden."""


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    lines = (re.sub(r"[ \t\r\f\v\xa0]+", " ", line).strip() for line in "".join(parser.parts).split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    pages = [
        f"[Seite {no}]\n{text.strip()}"
        for no, page in enumerate(PdfReader(BytesIO(data)).pages, 1)
        if (text := page.extract_text() or "").strip()
    ]
    return "\n\n".join(pages)


def to_text(data: bytes, content_type: str, charset: str | None) -> str:
    """Blockiert (pypdf) – im Executor aufrufen."""
    if data.startswith(b"%PDF-") or "pdf" in content_type:
        text = pdf_to_text(data)
    elif content_type.startswith("text/plain"):
        text = data.decode(charset or "utf-8", errors="replace")
    else:
        text = html_to_text(data.decode(charset or "utf-8", errors="replace"))
    return text[:MAX_CHARS]


async def download(session: aiohttp.ClientSession, url: str) -> tuple[bytes, str, str | None]:
    async with session.get(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True) as resp:
        if resp.status != 200:
            raise LinkError(f"HTTP {resp.status}")
        data = bytearray()
        async for chunk in resp.content.iter_chunked(256 * 1024):
            data += chunk
            if len(data) > MAX_BYTES:
                raise LinkError("Seite größer als 20 MB")
        return bytes(data), resp.content_type or "", resp.charset


class LinkCache:
    """Dateizugriffe blockieren und laufen im Executor."""

    def __init__(self, base: str | Path) -> None:
        self.base = Path(base)

    def _file(self, bgg_id: int, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        return self.base / str(int(bgg_id)) / ".links" / f"{digest}.txt"

    def get(self, bgg_id: int, url: str) -> tuple[str, bool] | None:
        """(Text, noch frisch?) oder None."""
        path = self._file(bgg_id, url)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8"), time.time() - path.stat().st_mtime < CACHE_SECONDS

    def put(self, bgg_id: int, url: str, text: str) -> None:
        path = self._file(bgg_id, url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
