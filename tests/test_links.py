import os
import time

import pytest

from core.links import CACHE_SECONDS, MAX_CHARS, LinkCache, html_to_text, to_text
from core.util import MAX_LINKS, normalize_links
from pdfs import make_pdf


def test_normalize_links():
    assert normalize_links([
        {"title": " Errata ", "url": " https://example.com/errata.pdf "},
        {"title": "", "url": "http://www.boardgamegeek.com/thread/1"},
        {"title": "leer", "url": ""},
    ]) == [
        {"title": "Errata", "url": "https://example.com/errata.pdf"},
        {"title": "boardgamegeek.com/thread/1", "url": "http://www.boardgamegeek.com/thread/1"},
    ]
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "https://a b.de", "example.com"):
        with pytest.raises(ValueError):
            normalize_links([{"url": bad}])
    with pytest.raises(ValueError):
        normalize_links([{"url": f"https://e.de/{i}"} for i in range(MAX_LINKS + 1)])


def test_html_to_text():
    html = """<html><head><title>x</title><style>p{}</style></head><body><nav>Menü</nav>
      <h1>Errata</h1><p>Seite 4:&nbsp;Der Räuber   darf <b>nicht</b> auf die Wüste.</p>
      <script>var x = 1;</script><ul><li>Punkt 1</li><li>Punkt 2</li></ul></body></html>"""
    assert html_to_text(html) == "Errata\n\nSeite 4: Der Räuber darf nicht auf die Wüste.\n\nPunkt 1\n\nPunkt 2"


def test_to_text_by_type():
    assert to_text(make_pdf("Almanach"), "application/octet-stream", None) == "[Seite 1]\nAlmanach"
    assert to_text("Grün".encode("latin-1"), "text/plain", "latin-1") == "Grün"
    assert to_text(b"<p>Hallo</p>", "text/html", None) == "Hallo"
    assert len(to_text(b"x" * (MAX_CHARS + 10), "text/plain", None)) == MAX_CHARS


def test_link_cache(tmp_path):
    cache = LinkCache(tmp_path)
    url = "https://example.com/errata"
    assert cache.get(13, url) is None
    cache.put(13, url, "Text")
    assert cache.get(13, url) == ("Text", True)
    old = time.time() - CACHE_SECONDS - 10
    path = next((tmp_path / "13" / ".links").iterdir())
    os.utime(path, (old, old))
    assert cache.get(13, url) == ("Text", False)
