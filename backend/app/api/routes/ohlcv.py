from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import pandas as pd

# Phase 1: Read-only OHLCV endpoint using existing Phase 0 loader (local file / cached logic)
# Future (Phase 2+): Add DB/Redis caching + parameter validation + metrics

router = APIRouter()

try:
    from services.ohlcv.ohlcv_loader import load_ohlcv  # type: ignore
except Exception:  # pragma: no cover - fallback stub
    load_ohlcv = None  # type: ignore

@router.get("/{symbol}")
async def get_ohlcv(symbol: str, bar: str = Query("15m"), limit: int = Query(200, ge=10, le=1000)):
    if load_ohlcv is None:
        raise HTTPException(status_code=500, detail="OHLCV loader unavailable")

    # Map simple symbol (BTC) to OKX instrument (BTC-USDT-SWAP) for now. Later add lookup table.
    instr = symbol.upper()
    if "-" not in instr:
        instr = f"{instr}-USDT-SWAP"

    df: Optional[pd.DataFrame] = load_ohlcv(instr, bar=bar, limit=limit)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No OHLCV data")

    # Minimal response (avoid huge payload); streamlit currently needs full rows, keep raw for now
    records = df.to_dict(orient="records")
    return {"symbol": symbol.upper(), "instrument": instr, "bar": bar, "count": len(records), "data": records}
