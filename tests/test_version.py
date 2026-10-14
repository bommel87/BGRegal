"""Die Versionsnummer muss überall gleich sein (Manifest, Konstante, User-Agent, Frontend-Imports)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1] / "custom_components" / "bgregal"


def test_versions_match():
    version = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert f'VERSION = "{version}"' in (ROOT / "const.py").read_text(encoding="utf-8")
    assert f"BGRegal/{version}" in (ROOT / "core" / "client.py").read_text(encoding="utf-8")
    for js in ("bgregal-panel.js", "bgregal-card.js"):
        text = (ROOT / "frontend" / js).read_text(encoding="utf-8")
        assert f"bgregal-common.js?v={version}" in text, js
