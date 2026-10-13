"""Fehler der BGG-Anbindung."""
from __future__ import annotations


class BggError(Exception):
    """Allgemeiner Fehler bei der Abfrage von BGG."""


class BggAuthError(BggError):
    """Token fehlt oder ist ungültig."""


class BggNotFoundError(BggError):
    """Den BGG-Benutzer gibt es nicht."""
