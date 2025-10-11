"""Price fetching utilities with multi-provider fallback and rate-limit resilience.

Providers order (default): CoinGecko -> OKX -> CoinMarketCap (if CMC_API_KEY set).
Exposed function: fetch_prices_and_changes(coins, force=False)
Return signature unchanged for backward compatibility.
"""

import json
import os
import time
import random
import requests
from typing import Dict, List, Tuple
from redis_cache import cache_prices, redis_diagnostics  # added diagnostics import


LAST_PRICE_FILE = "last_prices.json"
_LAST_PRICES: Dict[str, float] = {}
_LAST_PRICE_DATA: Dict[str, dict] = {}
_LAST_FETCH_TS = 0
_MIN_FETCH_INTERVAL = int(os.getenv("PRICE_MIN_FETCH_INTERVAL", "45"))  # default 45s

# Cooldown tracking per provider after rate limit / hard failure
_PROVIDER_COOLDOWN: Dict[str, float] = {}
_PROVIDER_ORDER_DEFAULT = ["coingecko", "okx", "cmc"]

# Mapping code coin id -> symbol for exchanges
_COIN_ID_TO_SYMBOL = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "binancecoin": "BNB",
    "bnb": "BNB",
    "chainlink": "LINK",
    "link": "LINK",
    "tether": "USDT",
    "solana": "SOL",
    "sol": "SOL",
}

class ProviderError(Exception):
    pass

def _load_last_prices_from_file():
    global _LAST_PRICES, _LAST_PRICE_DATA
    if os.path.exists(LAST_PRICE_FILE):
        try:
            with open(LAST_PRICE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _LAST_PRICES = data.get('prices', {}) or {}
            _LAST_PRICE_DATA = data.get('price_data', {}) or {}
        except Exception:
            _LAST_PRICES = {}
            _LAST_PRICE_DATA = {}

def _persist_last_prices():
    try:
        with open(LAST_PRICE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'prices': _LAST_PRICES,
                'price_data': _LAST_PRICE_DATA,
                'updated_at': int(time.time())
            }, f)
    except Exception:
        pass

def init_price_cache():
    _load_last_prices_from_file()
    # Debug redis diagnostics once at init (non-fatal)
    try:
        diag = redis_diagnostics()
        if not diag.get("import_ok"):
            print(f"[DEBUG] Redis diagnostics (import missing): {diag}")
        else:
            print(f"[DEBUG] Redis diagnostics: {diag}")
    except Exception as e:
        print(f"[DEBUG] Redis diagnostics fetch failed: {e}")

def get_last_prices():
    return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA)

def _set_cooldown(provider: str, seconds: int):
    _PROVIDER_COOLDOWN[provider] = time.time() + seconds

def _on_rate_limit(provider: str):
    # Cooldown with exponential-ish backoff bounded
    base = 120  # 2 minutes base
    jitter = random.randint(0, 30)
    _set_cooldown(provider, base + jitter)

def _provider_allowed(provider: str) -> bool:
    until = _PROVIDER_COOLDOWN.get(provider, 0)
    return time.time() > until

def _fetch_from_coingecko(coins: List[str]) -> Tuple[Dict[str, float], Dict[str, dict]]:
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins),
        "price_change_percentage": "1h,24h,7d,30d"
    }
    r = requests.get(url, params=params, timeout=20)
    if r.status_code == 429:
        _on_rate_limit("coingecko")
        raise ProviderError("coingecko rate limited (429)")
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        # Some error schemas return dict with 'status' etc.
        raise ProviderError(f"coingecko unexpected schema: {type(data).__name__}")
    prices = {}
    meta = {}
    for item in data:
        cid = item.get('id')
        if not cid:
            continue
        price = float(item.get('current_price') or 0.0)
        prices[cid] = price
        meta[cid] = {
            'price': price,
            'change_1d': item.get('price_change_percentage_24h', 0) or 0,
            'change_7d': item.get('price_change_percentage_7d_in_currency', 0) or 0,
            'change_30d': item.get('price_change_percentage_30d_in_currency', 0) or 0,
            'image': item.get('image', ''),
            'source': 'coingecko'
        }
    if not prices:
        raise ProviderError("coingecko returned no prices")
    return prices, meta

def _fetch_from_okx(coins: List[str]) -> Tuple[Dict[str, float], Dict[str, dict]]:
    prices = {}
    meta = {}
    for cid in coins:
        sym = _COIN_ID_TO_SYMBOL.get(cid, cid.upper())
        inst = f"{sym}-USDT"
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst}"
        r = requests.get(url, timeout=15)
        if r.status_code == 429:
            _on_rate_limit("okx")
            raise ProviderError("okx rate limited (429)")
        r.raise_for_status()
        data = r.json().get('data', [])
        if not data:
            continue
        ticker = data[0]
        last = float(ticker.get('last', 0) or 0)
        open24h = float(ticker.get('open24h', 0) or 0)
        change_1d = ((last - open24h) / open24h * 100) if open24h > 0 else 0
        prices[cid] = last
        meta[cid] = {
            'price': last,
            'change_1d': change_1d,
            'change_7d': 0,
            'change_30d': 0,
            'image': '',
            'source': 'okx'
        }
    if not prices:
        raise ProviderError("okx returned no prices")
    return prices, meta

def _fetch_from_cmc(coins: List[str]) -> Tuple[Dict[str, float], Dict[str, dict]]:
    api_key = os.getenv("CMC_API_KEY")
    if not api_key:
        raise ProviderError("cmc api key missing")
    # Convert ids to symbols for CMC
    symbols = []
    id_to_symbol_map = {}
    for cid in coins:
        sym = _COIN_ID_TO_SYMBOL.get(cid, cid.upper())
        symbols.append(sym)
        id_to_symbol_map[sym] = cid
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    params = {"symbol": ",".join(symbols), "convert": "USD"}
    headers = {"X-CMC_PRO_API_KEY": api_key}
    r = requests.get(url, params=params, headers=headers, timeout=25)
    if r.status_code == 429:
        _on_rate_limit("cmc")
        raise ProviderError("cmc rate limited (429)")
    r.raise_for_status()
    data = r.json().get('data', {})
    prices = {}
    meta = {}
    for sym, payload in data.items():
        quote = payload.get('quote', {}).get('USD', {})
        price = float(quote.get('price', 0) or 0)
        cid = id_to_symbol_map.get(sym, sym.lower())
        prices[cid] = price
        meta[cid] = {
            'price': price,
            'change_1d': quote.get('percent_change_24h', 0) or 0,
            'change_7d': quote.get('percent_change_7d', 0) or 0,
            'change_30d': quote.get('percent_change_30d', 0) or 0,
            'image': '',
            'source': 'cmc'
        }
    if not prices:
        raise ProviderError("cmc returned no prices")
    return prices, meta

def _provider_order():
    env_order = os.getenv("PRICE_PROVIDER_ORDER")
    if env_order:
        return [p.strip() for p in env_order.split(',') if p.strip()]
    return list(_PROVIDER_ORDER_DEFAULT)

def fetch_prices_and_changes(coins: List[str], force: bool = False) -> tuple[Dict[str, float], Dict[str, dict], bool, str]:
    global _LAST_PRICES, _LAST_PRICE_DATA, _LAST_FETCH_TS
    now = time.time()

    # Sanitize legacy/corrupted in-memory state if a prior run stored the 4-element list
    # structure (prices, meta, updated_local, errors) into _LAST_PRICES by mistake.
    if isinstance(_LAST_PRICES, list) and len(_LAST_PRICES) == 4 \
            and isinstance(_LAST_PRICES[0], dict) and isinstance(_LAST_PRICES[1], dict):
        try:
            prices_part, meta_part, _upd, _errs = _LAST_PRICES
            _LAST_PRICES = prices_part  # fix shape
            if not _LAST_PRICE_DATA:
                _LAST_PRICE_DATA = meta_part
        except Exception:
            pass
    if not coins:
        return {}, {}, False, "Không có coin để fetch"
    if not force and _LAST_PRICES and (now - _LAST_FETCH_TS) < _MIN_FETCH_INTERVAL:
        return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, "Dùng cache (interval)"

    def _loader_core():
        merged_prices: Dict[str, float] = {}
        merged_meta: Dict[str, dict] = {}
        errors = []
        updated_local = False
        for provider in _provider_order():
            if not _provider_allowed(provider):
                continue
            try:
                if provider == 'coingecko':
                    p, m = _fetch_from_coingecko(coins)
                elif provider == 'okx':
                    p, m = _fetch_from_okx(coins)
                elif provider == 'cmc':
                    p, m = _fetch_from_cmc(coins)
                else:
                    continue
                for c in coins:
                    if c in p and c not in merged_prices:
                        merged_prices[c] = p[c]
                        merged_meta[c] = m.get(c, {'price': p[c], 'change_1d':0,'change_7d':0,'change_30d':0,'image':'','source':provider})
                updated_local = True
                if len(merged_prices) == len(coins):
                    break
            except Exception as e:  # Continue to next provider
                errors.append(f"{provider}:{e}")
                continue
        if not merged_prices:
            if _LAST_PRICES:
                return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, f"Providers fail ({'; '.join(errors)}) – dùng cache"
            return {}, {}, False, f"Providers fail, không có cache ({'; '.join(errors)})"
        return merged_prices, merged_meta, updated_local, errors

    # Apply redis read-through if available (key per coin set) - TTL 60s
    if cache_prices and not force:
        result = cache_prices(coins, lambda: _loader_core(), ttl=60)
        # result can be tuple (original) OR list (JSON roundtrip of tuple) OR legacy prices-only.
        structured = False
        if isinstance(result, (tuple, list)) and len(result) == 4 \
                and isinstance(result[0], dict) and isinstance(result[1], dict):
            merged_prices, merged_meta, updated_local, errors = result  # type: ignore
            structured = True
            print("[DEBUG][prices] cache structured result (tuple/list of 4)")
        elif isinstance(result, dict):
            merged_prices, merged_meta, updated_local, errors = result, {}, True, []
            print("[DEBUG][prices] cache simple dict result (prices only)")
        else:
            # Unexpected shape – fall back to loader core directly (force rebuild)
            print(f"[DEBUG][prices] unexpected cached shape: {type(result)} -> fallback reload")
            merged_prices, merged_meta, updated_local, errors = _loader_core()
    else:
        merged_prices, merged_meta, updated_local, errors = _loader_core()
        print("[DEBUG] fetched prices directly without redis")

    if not merged_prices:
        print("[DEBUG] No prices fetched")
        return merged_prices, merged_meta, False, errors if isinstance(errors, str) else "; ".join(errors)

    # Backfill missing or zero prices from last known snapshot to avoid zeros in UI
    try:
        for cid in coins:
            last_price = _LAST_PRICES.get(cid, 0.0) if isinstance(_LAST_PRICES, dict) else 0.0
            if cid not in merged_prices:
                if last_price and last_price > 0:
                    merged_prices[cid] = float(last_price)
                    merged_meta[cid] = merged_meta.get(cid, {
                        'price': float(last_price), 'change_1d': 0, 'change_7d': 0, 'change_30d': 0, 'image': '', 'source': 'cache'
                    })
            else:
                if float(merged_prices.get(cid, 0.0) or 0.0) <= 0 and last_price and last_price > 0:
                    merged_prices[cid] = float(last_price)
                    m = merged_meta.get(cid) or {}
                    m['price'] = float(last_price)
                    m['source'] = m.get('source', 'cache')
                    merged_meta[cid] = m
    except Exception:
        pass

    _LAST_PRICES = merged_prices
    _LAST_PRICE_DATA = merged_meta
    _LAST_FETCH_TS = now
    _persist_last_prices()
    srcs = sorted({meta.get('source','?') for meta in merged_meta.values()})
    return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), updated_local, "Nguồn: " + ",".join(srcs)
