from fastapi import APIRouter

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.get("/metrics")
def list_metrics(product: str | None = None, channel: str | None = None) -> list[dict]:
    query = get_supabase().table("marketing_metrics").select("*").order("metric_date")
    if product:
        query = query.eq("product", product)
    if channel:
        query = query.eq("channel", channel)
    return query.execute().data
