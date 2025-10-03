import json
import os
import time
import requests
from typing import Dict, List

LAST_PRICE_FILE = "last_prices.json"
_LAST_PRICES: Dict[str, float] = {}
_LAST_PRICE_DATA: Dict[str, dict] = {}
_LAST_FETCH_TS = 0
_MIN_FETCH_INTERVAL = 15  # giây hạn chế spam

class CoinGeckoError(Exception):
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

def fetch_prices_and_changes(coins: List[str], force: bool = False) -> tuple[Dict[str, float], Dict[str, dict], bool, str]:
    """Trả về (prices, price_data, updated, message).
    - prices: dict {coin: price}
    - price_data: dict {coin: {...changes...}}
    - updated: True nếu có dữ liệu mới, False nếu dùng cache cũ
    - message: thông báo lỗi / trạng thái
    """
    global _LAST_PRICES, _LAST_PRICE_DATA, _LAST_FETCH_TS
    now = time.time()
    if not force and (now - _LAST_FETCH_TS) < _MIN_FETCH_INTERVAL and _LAST_PRICES:
        return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, "Dùng cache trong khoảng thời gian tối thiểu"

    if not coins:
        return {}, {}, False, "Không có coin để fetch"

    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coins),
        "price_change_percentage": "1h,24h,7d,30d"
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            raise CoinGeckoError("Rate limited (429)")
        r.raise_for_status()
        data = r.json()
        prices = {}
        price_data = {}
        for item in data:
            cid = item.get('id')
            if not cid:
                continue
            price = float(item.get('current_price') or 0.0)
            prices[cid] = price
            price_data[cid] = {
                'price': price,
                'change_1d': item.get('price_change_percentage_24h', 0) or 0,
                'change_7d': item.get('price_change_percentage_7d_in_currency', 0) or 0,
                'change_30d': item.get('price_change_percentage_30d_in_currency', 0) or 0,
                'image': item.get('image', '')
            }
        if not prices:
            raise CoinGeckoError("Không nhận được dữ liệu giá từ API")
        _LAST_PRICES = prices
        _LAST_PRICE_DATA = price_data
        _LAST_FETCH_TS = now
        _persist_last_prices()
        return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), True, "Cập nhật mới thành công"
    except Exception as e:
        # Dùng dữ liệu cũ nếu có
        if _LAST_PRICES:
            return dict(_LAST_PRICES), dict(_LAST_PRICE_DATA), False, f"Lỗi API: {e}. Dùng giá cũ"
        return {}, {}, False, f"Lỗi API và không có cache: {e}"
