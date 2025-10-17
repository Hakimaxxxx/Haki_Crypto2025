"""
Simple test harness template. Place under `tests/` and adapt to project test runner (pytest recommended).
"""
import json
from pathlib import Path


def test_sample_json_load():
    p = Path("./last_prices.json")
    assert p.exists(), "last_prices.json must exist for this test"
    data = json.loads(p.read_text())
    assert isinstance(data, dict)
