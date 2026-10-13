"""Macht das Kernpaket ohne Home Assistant importierbar (als `core`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "bgregal"))

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
