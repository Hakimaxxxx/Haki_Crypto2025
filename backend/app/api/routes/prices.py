from fastapi import APIRouter, Query
from typing import List, Optional
from ...schemas.base import PriceSnapshot
from ...services.prices_service import get_prices, get_price_ttl, get_cache_ts

router = APIRouter()

@router.get("/spot", response_model=dict)
async def get_spot_prices(symbols: Optional[str] = Query(None, description="Comma separated symbols (e.g. BTC,ETH,SOL)")):
    symbol_list: Optional[List[str]] = None
    if symbols:
        symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]
    snaps = get_prices(symbol_list)
    # Serialize PriceSnapshot objects
    serialized = {k: v.model_dump() for k, v in snaps.items()}
    return {
        "count": len(serialized),
        "prices": serialized,
        "ttl": get_price_ttl(),
        "generated_at": get_cache_ts()
    }
