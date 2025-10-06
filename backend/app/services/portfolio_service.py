from __future__ import annotations
import os, json, time
from typing import Dict
from ..schemas.base import PortfolioMeta, PortfolioPosition, PortfolioMetaResponse

DATA_FILE = os.getenv('DATA_FILE', 'data.json')
AVG_FILE = os.getenv('AVG_PRICE_FILE', 'avg_price.json')
LAST_PRICE_FILE = os.getenv('LAST_PRICE_FILE', 'last_prices.json')

_PORT_CACHE = {"data": None, "ts": 0.0}
_PORT_TTL = 20


def _load_json(path: str):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _assemble_domain() -> PortfolioMeta:
    holdings = _load_json(DATA_FILE)
    avg_prices = _load_json(AVG_FILE)
    raw_prices = _load_json(LAST_PRICE_FILE)
    if isinstance(raw_prices, dict) and 'prices' in raw_prices:
        prices_block = raw_prices.get('prices', {})
        changes_block = raw_prices.get('price_data', {})
    else:
        prices_block = raw_prices
        changes_block = {}
    prices_out = {}
    for k, v in prices_block.items():
        try:
            if isinstance(v, dict):
                val = v.get('price') or v.get('last') or v.get('value') or v.get('close')
            else:
                val = v
            prices_out[k.upper()] = float(val)
        except Exception:
            prices_out[k.upper()] = 0.0

    positions = []
    total_value = 0.0
    total_invested = 0.0
    for sym, amt in holdings.items():
        try:
            amt_f = float(amt)
        except Exception:
            amt_f = 0.0
        avg_cost = float(avg_prices.get(sym, 0.0) or 0.0)
        price_now = float(prices_out.get(sym.upper(), 0.0))
        value = amt_f * price_now
        invested = amt_f * avg_cost
        pnl_abs = value - invested
        pnl_pct = (pnl_abs / invested * 100) if invested > 0 else None
        total_value += value
        total_invested += invested
        positions.append(PortfolioPosition(
            symbol=sym.upper(),
            holding=amt_f,
            avg_cost=avg_cost,
            value=value,
            pnl_abs=pnl_abs,
            pnl_pct=pnl_pct
        ))
    total_pnl_abs = total_value - total_invested
    total_pnl_pct = (total_pnl_abs / total_invested * 100) if total_invested > 0 else None
    meta = PortfolioMeta(
        generated_at=int(time.time()),
        positions=positions,
        total_value=total_value,
        total_pnl_abs=total_pnl_abs,
        total_pnl_pct=total_pnl_pct
    )
    return meta


def _get_cached_meta() -> PortfolioMeta:
    now = time.time()
    if not _PORT_CACHE['data'] or now - _PORT_CACHE['ts'] > _PORT_TTL:
        _PORT_CACHE['data'] = _assemble_domain()
        _PORT_CACHE['ts'] = now
    return _PORT_CACHE['data']


def get_portfolio_meta() -> PortfolioMetaResponse:
    meta = _get_cached_meta()
    return PortfolioMetaResponse(data=meta, source="file")


def portfolio_ttl() -> int:
    return _PORT_TTL
