from fastapi import APIRouter
import time

router = APIRouter()
_start_time = time.time()

@router.get("/")
async def health_root():
    return {"status": "ok"}

@router.get("/live")
async def liveness():
    return {"live": True}

@router.get("/ready")
async def readiness():
    # Placeholder checks (extend Phase 2: DB / Redis)
    uptime = time.time() - _start_time
    return {"ready": True, "uptime_sec": int(uptime)}
