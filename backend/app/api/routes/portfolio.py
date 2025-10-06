from fastapi import APIRouter
from ...services.portfolio_service import get_portfolio_meta, portfolio_ttl

router = APIRouter()

@router.get("/meta")
async def get_portfolio_meta_route():
    resp = get_portfolio_meta()
    return {"ttl": portfolio_ttl(), "data": resp.data.model_dump(), "source": resp.source}
