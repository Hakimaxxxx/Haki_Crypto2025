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
    if not coins:
        return {}, {}, False, "Không có coin để fetch"
    if not force and _LAST_PRICES and (now - _LAST_FETCH_TS) < _MIN_FETCH_INTERVAL:
        return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, "Dùng cache (interval)"

    merged_prices: Dict[str, float] = {}
    merged_meta: Dict[str, dict] = {}
    errors = []
    updated = False
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
            # Merge; prefer earlier providers, fill missing coins from later ones
            for c in coins:
                if c in p and c not in merged_prices:
                    merged_prices[c] = p[c]
                    merged_meta[c] = m.get(c, {'price': p[c], 'change_1d':0,'change_7d':0,'change_30d':0,'image':'','source':provider})
            updated = True
            # If we already have all coins, break
            if len(merged_prices) == len(coins):
                break
        except Exception as e:  # Continue to next provider
            errors.append(f"{provider}:{e}")
            continue

    if not merged_prices:
        # fallback to cache
        if _LAST_PRICES:
            return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, f"Providers fail ({'; '.join(errors)}) – dùng cache"
        return {}, {}, False, f"Providers fail, không có cache ({'; '.join(errors)})"

    _LAST_PRICES = merged_prices
    _LAST_PRICE_DATA = merged_meta
    _LAST_FETCH_TS = now
    _persist_last_prices()
    srcs = sorted({meta.get('source','?') for meta in merged_meta.values()})
    return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), updated, "Nguồn: " + ",".join(srcs)
