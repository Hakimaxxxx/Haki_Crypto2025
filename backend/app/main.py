from fastapi import FastAPI
from .services.scheduler import register_task, start_all, list_tasks
from .services.alerts_service import evaluate_rules, list_alerts, load_rules
from .services.prices_service import get_prices
from fastapi.middleware.cors import CORSMiddleware
from .api.routes.health import router as health_router
from .api.routes.prices import router as prices_router
from .api.routes.ohlcv import router as ohlcv_router
from .api.routes.whales import router as whales_router
from .api.routes.portfolio import router as portfolio_router

app = FastAPI(title="Crypto Analytics API", version="0.1.0")

# Basic CORS (loosen for now; tighten later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/health", tags=["health"]) 
app.include_router(prices_router, prefix="/prices", tags=["prices"]) 
app.include_router(ohlcv_router, prefix="/ohlcv", tags=["ohlcv"]) 
app.include_router(whales_router, prefix="/whales", tags=["whales"]) 
app.include_router(portfolio_router, prefix="/portfolio", tags=["portfolio"]) 
alerts_router = FastAPI()

from fastapi import APIRouter, Query
alerts_api = APIRouter()

@alerts_api.get("/alerts")
async def get_alerts(limit: int = Query(100, ge=1, le=300)):
    return {"count": limit, "alerts": list_alerts(limit)}

app.include_router(alerts_api, tags=["alerts"])

@app.get("/")
async def root():
    return {"status": "ok", "message": "Crypto Analytics Backend", "version": app.version}

@app.on_event("startup")
async def _startup():
    # Đăng ký các task nền (Phase 2 skeleton)
    def warm_prices():
        # Gọi get_prices để refresh cache định kỳ
        get_prices()
    def eval_rules_task():
        evaluate_rules()
    register_task("warm_prices", interval=25, func=warm_prices, jitter=0.2)
    register_task("evaluate_rules", interval=30, func=eval_rules_task, jitter=0.15)
    # Sample default rule load (placeholder)
    load_rules([
        {"id": "demo_whale_eth", "type": "whale_large", "symbol": "ETH", "min_amount_usd": 250000, "window_sec": 900},
        {"id": "demo_price_btc", "type": "price_move", "symbol": "BTC", "pct_move": 1.5, "window_sec": 1800}
    ])
    start_all()

@app.get("/tasks")
async def tasks_status():
    return {"tasks": list_tasks()}
