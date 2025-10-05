from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.health import router as health_router
from app.api.routes.prices import router as prices_router

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

@app.get("/")
async def root():
    return {"status": "ok", "message": "Crypto Analytics Backend", "version": app.version}
