from __future__ import annotations
import os, json, time
from typing import Dict, Tuple, Optional, List
from ..schemas.base import PriceSnapshot
try:  # lấy COIN_LIST từ config gốc
    from config import COIN_LIST  # type: ignore
except Exception:
    COIN_LIST = []

# Map coin_id -> symbol & symbol -> coin_id
_ID_TO_SYMBOL = {cid: sym for cid, sym in COIN_LIST}
_SYMBOL_TO_ID = {sym: cid for cid, sym in COIN_LIST}

LAST_PRICE_FILE = os.getenv("LAST_PRICE_FILE", "last_prices.json")
PRICE_TTL = 30

_price_cache: dict = {"data": {}, "ts": 0.0}


def _load_last_prices_raw() -> Tuple[Dict, Dict]:
    if not os.path.exists(LAST_PRICE_FILE):
        return {}, {}
    try:
        with open(LAST_PRICE_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception:
        return {}, {}
    prices_block, changes_block = {}, {}
    if isinstance(raw, dict) and 'prices' in raw:
        prices_block = raw.get('prices', {})
        changes_block = raw.get('price_data', {})
    else:
        prices_block = raw
    return prices_block, changes_block


def _normalize_price_entry(v) -> float:
    if isinstance(v, dict):
        for cand in ('price','last','value','close'):
            if cand in v:
                try:
                    return float(v[cand])
                except Exception:
                    return 0.0
        for val in v.values():
            if isinstance(val, (int, float)):
                return float(val)
        return 0.0
    try:
        return float(v)
    except Exception:
        return 0.0


def _rebuild_cache():
    prices_block, changes_block = _load_last_prices_raw()
    norm: Dict[str, PriceSnapshot] = {}
    ts_now = int(time.time())
    for coin_id, v in prices_block.items():
        coin_id_l = str(coin_id).lower()
        display_symbol = _ID_TO_SYMBOL.get(coin_id_l) or _ID_TO_SYMBOL.get(coin_id) or coin_id.upper()
        price = _normalize_price_entry(v)
        ch_src = changes_block.get(coin_id_l) or changes_block.get(coin_id) or {}
        snap = PriceSnapshot(
            symbol=display_symbol,
            coin_id=coin_id_l,
            price=price,
            change_1d=float(ch_src.get('change_1d', ch_src.get('change24h', 0) or ch_src.get('change_24h', 0) or 0) or 0),
            change_7d=float(ch_src.get('change_7d', ch_src.get('change7d', 0) or 0) or 0),
            change_30d=float(ch_src.get('change_30d', ch_src.get('change30d', 0) or 0) or 0),
            ts=ts_now
        )
        norm[display_symbol] = snap
    _price_cache['data'] = norm
    _price_cache['ts'] = time.time()


def get_prices(symbols: Optional[List[str]] = None) -> Dict[str, PriceSnapshot]:
    now = time.time()
    if not _price_cache['data'] or now - _price_cache['ts'] > PRICE_TTL:
        _rebuild_cache()
    data: Dict[str, PriceSnapshot] = _price_cache['data']
    if symbols:
        symbols_up = {s.upper() for s in symbols}
        # Symbols có thể là display (BTC) hoặc coin id (bitcoin)
        out: Dict[str, PriceSnapshot] = {}
        for k, snap in data.items():
            if k.upper() in symbols_up or (snap.coin_id and snap.coin_id.upper() in symbols_up):
                out[k] = snap
        return out
    return data


def get_price_ttl() -> int:
    return PRICE_TTL


def get_cache_ts() -> float:
    return _price_cache.get('ts', 0.0)
