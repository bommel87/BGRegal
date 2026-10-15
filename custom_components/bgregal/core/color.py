"""Hauptfarbe eines Covers für die Seitenansicht der Kartons."""
from __future__ import annotations

import io


def dominant_color(data: bytes) -> str | None:
    """Häufigste Farbe des Bildes als #rrggbb; fast weiße/schwarze Ränder zählen nur notfalls."""
    from PIL import Image  # noqa: PLC0415 - Pillow bringt Home Assistant mit

    try:
        with Image.open(io.BytesIO(data)) as img:
            small = img.convert("RGB").resize((48, 48))
    except (OSError, ValueError):
        return None
    palette = small.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    colors = palette.getpalette() or []
    counts = sorted(palette.getcolors() or [], reverse=True)  # [(Anzahl, Index)]
    rgb = [tuple(colors[i * 3 : i * 3 + 3]) for _, i in counts]
    if not rgb:
        return None

    def plain(c: tuple[int, ...]) -> bool:
        return min(c) > 225 or max(c) < 25

    best = next((c for c in rgb if not plain(c)), rgb[0])
    return "#{:02x}{:02x}{:02x}".format(*best)
