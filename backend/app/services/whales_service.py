from __future__ import annotations
import time
from typing import Dict, List
from ..schemas.base import WhaleEvent

try:
    from services.whale.whale_loader import load_whales_for_symbol, normalize_events, as_overlay_events  # type: ignore
except Exception:  # pragma: no cover
    load_whales_for_symbol = None  # type: ignore
    normalize_events = None  # type: ignore
    as_overlay_events = None  # type: ignore

_WHALE_CACHE: Dict[str, Dict] = {"data": {}, "ts": 0.0}
WHALE_TTL = 20


def _cache_key(symbol: str) -> str:
    return symbol.upper()


def _load_events(symbol: str) -> List[dict]:
    if load_whales_for_symbol is None:
        return []
    raw = load_whales_for_symbol(symbol.upper()) or []
    return raw


def get_whale_events(symbol: str) -> List[dict]:
    now = time.time()
    key = _cache_key(symbol)
    blob = _WHALE_CACHE['data'].get(key)
    if blob and now - blob['ts'] < WHALE_TTL:
        return blob['events']
    events = _load_events(symbol)
    _WHALE_CACHE['data'][key] = {'events': events, 'ts': now}
    return events


def get_whale_overlay(symbol: str) -> List[dict]:
    if as_overlay_events is None:
        return []
    events = get_whale_events(symbol)
    overlay = as_overlay_events(events)
    try:
        overlay.sort(key=lambda e: e.get('time'), reverse=True)
    except Exception:
        pass
    return overlay


def whale_ttl() -> int:
    return WHALE_TTL
