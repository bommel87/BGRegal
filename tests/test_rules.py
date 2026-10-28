import os

import pytest

from core.rules import MAX_BYTES, RuleBookError, RuleBooks, safe_name
from pdfs import make_pdf


def test_safe_name():
    assert safe_name("Catan.pdf") == "Catan.pdf"
    assert safe_name(r"C:\Downloads\Catan - Almanach.PDF") == "Catan - Almanach.pdf"
    assert safe_name("../../etc/passwd") == "passwd.pdf"
    assert safe_name("Spiel|<x>") == "Spielx.pdf"
    with pytest.raises(RuleBookError):
        safe_name("../.pdf")


def test_add_list_text_remove(tmp_path):
    books = RuleBooks(tmp_path)
    assert books.list(13) == [] and books.index() == {}
    assert books.add(13, "Catan.pdf", [make_pdf("Der Raeuber", "Seite zwei")]) == "Catan.pdf"
    books.add(13, "almanach.pdf", [make_pdf("Almanach")])
    assert [b["name"] for b in books.list(13)] == ["almanach.pdf", "Catan.pdf"]
    assert books.index() == {13: ["almanach.pdf", "Catan.pdf"]}

    text = books.text(13, "Catan.pdf")
    assert text == "[Seite 1]\nDer Raeuber\n\n[Seite 2]\nSeite zwei"
    cache = tmp_path / "13" / ".text" / "Catan.txt"
    assert cache.read_text(encoding="utf-8") == text

    # Gleicher Name ersetzt das PDF und verwirft den alten Text
    books.add(13, "Catan.pdf", [make_pdf("Neu")])
    assert not cache.exists()
    assert books.text(13, "Catan.pdf") == "[Seite 1]\nNeu"

    books.remove(13, "Catan.pdf")
    books.remove(13, "almanach.pdf")
    assert not (tmp_path / "13").exists()
    with pytest.raises(RuleBookError):
        books.remove(13, "Catan.pdf")


def test_rejects_bad_uploads(tmp_path):
    books = RuleBooks(tmp_path)
    with pytest.raises(RuleBookError, match="kein PDF"):
        books.add(1, "x.pdf", [b"<html>"])
    with pytest.raises(RuleBookError, match="leer"):
        books.add(1, "x.pdf", [])
    with pytest.raises(RuleBookError, match="100 MB"):
        books.add(1, "x.pdf", [b"%PDF-" + b"0" * MAX_BYTES])
    assert books.list(1) == []
    assert not [p for p in (tmp_path / "1").iterdir()]  # keine Reste
    with pytest.raises(RuleBookError):
        books.path(1, "../bgregal.db")


def test_cache_renewed_when_pdf_newer(tmp_path):
    books = RuleBooks(tmp_path)
    books.add(5, "r.pdf", [make_pdf("Alt")])
    assert books.text(5, "r.pdf") == "[Seite 1]\nAlt"
    cache = tmp_path / "5" / ".text" / "r.txt"
    cache.write_text("veraltet", encoding="utf-8")
    old = cache.stat().st_mtime - 10
    os.utime(cache, (old, old))
    assert books.text(5, "r.pdf") == "[Seite 1]\nAlt"
