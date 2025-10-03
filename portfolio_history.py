import json
import os
import time
from typing import List, Dict
from config import HISTORY_FILE

# Simple in-memory cache
_HISTORY_CACHE: List[Dict] = []
_HISTORY_LAST_LOAD = 0
_CACHE_TTL = 30  # seconds


def load_history(force: bool = False) -> List[Dict]:
    global _HISTORY_CACHE, _HISTORY_LAST_LOAD
    now = time.time()
    if not force and _HISTORY_CACHE and (now - _HISTORY_LAST_LOAD) < _CACHE_TTL:
        return _HISTORY_CACHE
    if not os.path.exists(HISTORY_FILE):
        _HISTORY_CACHE = []
        _HISTORY_LAST_LOAD = now
        return _HISTORY_CACHE
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            _HISTORY_CACHE = json.load(f)
            _HISTORY_LAST_LOAD = now
    except Exception:
        _HISTORY_CACHE = []
    return _HISTORY_CACHE


def append_snapshot(docs: List[Dict]):
    """Append new snapshot docs (already validated externally)."""
    if not docs:
        return
    hist = load_history(force=True)
    # Avoid duplication by (timestamp, coin/null)
    existing_keys = {(d.get('timestamp'), d.get('coin')) for d in hist}
    new_clean = [d for d in docs if (d.get('timestamp'), d.get('coin')) not in existing_keys]
    if not new_clean:
        return
    hist.extend(new_clean)
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(hist, f)
    except Exception:
        pass


def filter_portfolio_totals(hist: List[Dict]):
    return [h for h in hist if 'coin' not in h]


def filter_coin_history(hist: List[Dict], coin_id: str):
    return [h for h in hist if h.get('coin') == coin_id]
