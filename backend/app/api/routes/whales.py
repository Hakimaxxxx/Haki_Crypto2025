from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict
from ...services.whales_service import get_whale_events, get_whale_overlay, whale_ttl

router = APIRouter()

@router.get("/{symbol}")
async def get_whales(symbol: str, limit: int = Query(120, ge=10, le=500)):
    events: List[Dict] = get_whale_events(symbol)
    if not events:
        raise HTTPException(status_code=404, detail="No whale events found")
    # Sort and slice
    def _ts(e: Dict):
        return e.get('ts') or e.get('timestamp') or e.get('time')
    try:
        events.sort(key=_ts, reverse=True)
    except Exception:
        pass
    sliced = events[:limit]
    for e in sliced:
        ts = e.get('ts')
        if hasattr(ts, 'isoformat'):
            e['ts'] = ts.isoformat()
    return {"symbol": symbol.upper(), "count": len(sliced), "ttl": whale_ttl(), "events": sliced}

@router.get("/{symbol}/overlay")
async def get_whales_overlay(symbol: str, limit: int = Query(120, ge=10, le=500)):
    overlay = get_whale_overlay(symbol)
    if not overlay:
        raise HTTPException(status_code=404, detail="No whale events found")
    return {"symbol": symbol.upper(), "count": min(len(overlay), limit), "ttl": whale_ttl(), "overlay": overlay[:limit]}
