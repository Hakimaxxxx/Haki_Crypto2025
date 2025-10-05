from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
import json, os

router = APIRouter()

DATA_FILE = "data.json"  # holdings (legacy)
LAST_PRICE_FILE = "last_prices.json"  # existing spot prices local cache

@router.get("/spot")
async def get_spot_prices(symbols: str = Query(None, description="Comma separated symbols (e.g. BTC,ETH,SOL)")):
    # Load local cache file (Phase 0 style) – to be replaced with DB in later phase
    if not os.path.exists(LAST_PRICE_FILE):
        raise HTTPException(status_code=404, detail="Price cache file not found")
    try:
        with open(LAST_PRICE_FILE, 'r', encoding='utf-8') as f:
            price_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot read price cache: {e}")

    if symbols:
        req = [s.strip().lower() for s in symbols.split(',') if s.strip()]
        filtered = {k: v for k, v in price_data.items() if k.lower() in req}
    else:
        filtered = price_data
    return {"count": len(filtered), "prices": filtered}
