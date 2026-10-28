"""Anleitungen: PDFs je Spiel speichern und ihren Text für Regelfragen auslesen.

Ablage: <Ordner>/<bgg_id>/<Name>.pdf, ausgelesener Text daneben in .text/<Name>.txt.
Ein Spiel kann mehrere PDFs haben (z. B. Regelheft und Almanach).
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

MAX_BYTES = 100 * 1024 * 1024
PDF_MAGIC = b"%PDF-"
TEXT_DIR = ".text"
_UNSAFE = re.compile(r"[^\w .()+-]+")


class RuleBookError(ValueError):
    """Ungültige Datei oder ungültiger Name."""


def safe_name(filename: str) -> str:
    """Dateiname ohne Pfad und Sonderzeichen, immer mit .pdf. Leer → RuleBookError."""
    stem = Path(filename.replace("\\", "/")).name
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    stem = _UNSAFE.sub("", stem).strip(" .")[:80]
    if not stem:
        raise RuleBookError("Ungültiger Dateiname")
    return f"{stem}.pdf"


def extract_text(pdf: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(pdf)
    pages = [
        f"[Seite {no}]\n{text.strip()}"
        for no, page in enumerate(reader.pages, 1)
        if (text := page.extract_text() or "").strip()
    ]
    return "\n\n".join(pages)


class RuleBooks:
    """Alle Methoden blockieren (Dateizugriff) und laufen im Executor."""

    def __init__(self, base: str | Path) -> None:
        self.base = Path(base)

    def _dir(self, bgg_id: int) -> Path:
        return self.base / str(int(bgg_id))

    def path(self, bgg_id: int, name: str) -> Path:
        """Pfad zu einem vorhandenen PDF; RuleBookError, wenn es fehlt."""
        if name != safe_name(name):
            raise RuleBookError("Ungültiger Dateiname")
        pdf = self._dir(bgg_id) / name
        if not pdf.is_file():
            raise RuleBookError("Anleitung nicht gefunden")
        return pdf

    def list(self, bgg_id: int) -> list[dict[str, Any]]:
        folder = self._dir(bgg_id)
        if not folder.is_dir():
            return []
        return [
            {"name": p.name, "size": p.stat().st_size}
            for p in sorted(folder.iterdir(), key=lambda p: p.name.lower())
            if p.is_file() and p.suffix == ".pdf"
        ]

    def index(self) -> dict[int, list[str]]:
        """BGG-ID → Dateinamen, nur Spiele mit Anleitung."""
        if not self.base.is_dir():
            return {}
        result = {}
        for folder in self.base.iterdir():
            if folder.is_dir() and folder.name.isdigit():
                if names := [f["name"] for f in self.list(int(folder.name))]:
                    result[int(folder.name)] = names
        return result

    def add(self, bgg_id: int, filename: str, chunks: Iterable[bytes]) -> str:
        """PDF speichern (gleicher Name ersetzt die alte Datei). Gibt den gespeicherten Namen zurück."""
        name = safe_name(filename)
        folder = self._dir(bgg_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".upload-{name}"
        size = 0
        try:
            with tmp.open("wb") as fh:
                for chunk in chunks:
                    if size == 0 and not chunk.startswith(PDF_MAGIC):
                        raise RuleBookError("Die Datei ist kein PDF")
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise RuleBookError("Die Datei ist größer als 100 MB")
                    fh.write(chunk)
            if size == 0:
                raise RuleBookError("Die Datei ist leer")
            tmp.replace(folder / name)
        finally:
            tmp.unlink(missing_ok=True)
        (folder / TEXT_DIR / f"{name[:-4]}.txt").unlink(missing_ok=True)
        return name

    def remove(self, bgg_id: int, name: str) -> None:
        pdf = self.path(bgg_id, name)
        pdf.unlink()
        (pdf.parent / TEXT_DIR / f"{pdf.stem}.txt").unlink(missing_ok=True)
        if not self.list(bgg_id):
            shutil.rmtree(pdf.parent, ignore_errors=True)

    def text(self, bgg_id: int, name: str) -> str:
        """Text eines PDFs; beim ersten Abruf ausgelesen und zwischengespeichert."""
        pdf = self.path(bgg_id, name)
        cache = pdf.parent / TEXT_DIR / f"{pdf.stem}.txt"
        if cache.is_file() and cache.stat().st_mtime >= pdf.stat().st_mtime:
            return cache.read_text(encoding="utf-8")
        text = extract_text(pdf)
        cache.parent.mkdir(exist_ok=True)
        cache.write_text(text, encoding="utf-8")
        return text
