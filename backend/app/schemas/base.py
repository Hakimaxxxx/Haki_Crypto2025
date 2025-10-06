from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
import datetime as dt

class APIModel(BaseModel):
    class Config:
        extra = 'ignore'
        validate_assignment = True

class PriceSnapshot(APIModel):
    symbol: str  # Display symbol, ví dụ: BTC
    coin_id: str | None = Field(None, description="Underlying coin id (coingecko id), ví dụ: bitcoin")
    price: float = Field(..., ge=0)
    change_1d: float | None = None
    change_7d: float | None = None
    change_30d: float | None = None
    ts: int = Field(..., description="Unix timestamp (seconds)")

class WhaleEvent(APIModel):
    symbol: str
    ts: int
    direction: str | None = Field(None, description="BUY/SELL/UNKNOWN")
    amount_token: float | None = None
    amount_usd: float | None = None
    tx_hash: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    chain: str | None = None

class OHLCVBar(APIModel):
    symbol: str
    ts_open: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str

class PortfolioPosition(APIModel):
    symbol: str
    holding: float = 0
    avg_cost: float | None = None
    value: float | None = None
    pnl_abs: float | None = None
    pnl_pct: float | None = None

class PortfolioMeta(APIModel):
    generated_at: int
    positions: List[PortfolioPosition]
    total_value: float | None = None
    total_pnl_abs: float | None = None
    total_pnl_pct: float | None = None

class PortfolioMetaResponse(APIModel):
    data: PortfolioMeta
    source: str

__all__ = [
    'PriceSnapshot', 'WhaleEvent', 'OHLCVBar', 'PortfolioPosition', 'PortfolioMeta', 'PortfolioMetaResponse'
]
