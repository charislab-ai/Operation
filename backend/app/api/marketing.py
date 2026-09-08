import mimetypes
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/marketing", tags=["marketing"])

PRODUCT_ASSETS_BUCKET = "product-assets"


@router.get("/metrics")
def list_metrics(product: str | None = None, channel: str | None = None) -> list[dict]:
    query = get_supabase().table("marketing_metrics").select("*").order("metric_date")
    if product:
        query = query.eq("product", product)
    if channel:
        query = query.eq("channel", channel)
    return query.execute().data


class ProductAssetOut(BaseModel):
    id: str
    product: str
    description: str
    url: str


@router.post("/assets", response_model=ProductAssetOut)
async def upload_product_asset(
    product: str = Form(...), description: str = Form(...), file: UploadFile = File(...)
) -> dict:
    """실제 앱 스크린샷을 등록한다 - MarketingWorker가 AI 생성 대신 실제 화면을 카드뉴스에 쓸 수 있게 함.
    description은 이 화면이 뭘 보여주는지(예: "벨소리 만들기 편집 화면") 최대한 구체적으로 적어야
    LLM이 적절한 슬라이드에 매칭할 수 있다.
    """
    image_bytes = await file.read()
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "image/png"
    ext = mimetypes.guess_extension(mime_type) or ".png"

    supabase = get_supabase()
    bucket = supabase.storage.from_(PRODUCT_ASSETS_BUCKET)
    # Storage 키는 ASCII만 허용됨(한글 파일명이면 InvalidKey 에러) - 원본 파일명은 버리고 UUID로만 구성
    storage_path = f"{uuid.uuid4()}{ext}"
    bucket.upload(storage_path, image_bytes, {"content-type": mime_type})
    url = bucket.get_public_url(storage_path)

    row = (
        supabase.table("product_assets")
        .insert({"product": product, "storage_path": storage_path, "description": description})
        .execute()
    )
    asset_id = row.data[0]["id"]
    return {"id": asset_id, "product": product, "description": description, "url": url}


@router.get("/assets", response_model=list[ProductAssetOut])
def list_product_assets(product: str | None = None) -> list[dict]:
    query = get_supabase().table("product_assets").select("id, product, description, storage_path")
    if product:
        query = query.eq("product", product)
    rows = query.order("created_at", desc=True).execute().data

    bucket = get_supabase().storage.from_(PRODUCT_ASSETS_BUCKET)
    return [
        {
            "id": r["id"],
            "product": r["product"],
            "description": r["description"],
            "url": bucket.get_public_url(r["storage_path"]),
        }
        for r in rows
    ]


class ProductAssetUpdate(BaseModel):
    description: str


@router.patch("/assets/{asset_id}", response_model=ProductAssetOut)
def update_product_asset(asset_id: str, payload: ProductAssetUpdate) -> dict:
    supabase = get_supabase()
    result = (
        supabase.table("product_assets")
        .update({"description": payload.description})
        .eq("id", asset_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="asset not found")
    row = result.data[0]
    bucket = supabase.storage.from_(PRODUCT_ASSETS_BUCKET)
    return {
        "id": row["id"],
        "product": row["product"],
        "description": row["description"],
        "url": bucket.get_public_url(row["storage_path"]),
    }


@router.delete("/assets/{asset_id}")
def delete_product_asset(asset_id: str) -> dict:
    supabase = get_supabase()
    row = supabase.table("product_assets").select("storage_path").eq("id", asset_id).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="asset not found")
    storage_path = row.data[0]["storage_path"]
    supabase.table("product_assets").delete().eq("id", asset_id).execute()
    supabase.storage.from_(PRODUCT_ASSETS_BUCKET).remove([storage_path])
    return {"status": "deleted"}
