"""
Service template for adding small reusable logic (e.g., whale loader, ohlcv loader).
- Place under `services/<domain>/` and expose small, well-documented functions.
- Keep I/O and network operations behind small functions and annotate return types.
"""
from __future__ import annotations
import os
import json
from typing import List, Dict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load_json_safe(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def normalize_whale_events(raw_events: List[Dict]) -> List[Dict]:
    """Convert chain-specific events to canonical shape:
    {
      "ts": int,  # unix epoch seconds
      "symbol": str,  # token symbol used in the app
      "value_usd": float,
      "type": str,  # 'transfer' | 'trade' | ...
      "direction": 'in'|'out'
    }
    """
    out: List[Dict] = []
    for e in raw_events:
        # implement minimal mapping, be defensive
        try:
            ts = int(e.get("ts") or e.get("time") or 0)
            symbol = e.get("symbol") or e.get("token") or ""
            value = float(e.get("value_usd") or e.get("usd") or 0.0)
            direction = e.get("direction") or e.get("dir") or "out"
            out.append({"ts": ts, "symbol": symbol, "value_usd": value, "type": e.get("type", "transfer"), "direction": direction})
        except Exception:
            continue
    return out
