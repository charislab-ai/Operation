from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/products", tags=["products"])


class ProductOut(BaseModel):
    id: str
    name: str
    ios_url: str | None
    android_url: str | None
    brand_color: str | None
    description: str | None


class ProductUpdate(BaseModel):
    ios_url: str | None = None
    android_url: str | None = None
    brand_color: str | None = None
    description: str | None = None


@router.get("", response_model=list[ProductOut])
def list_products() -> list[dict]:
    """앱관리 화면용 - 실제 출시된 앱 목록과 스토어 링크/브랜드 컬러/설명.

    MarketingWorker가 카드뉴스 생성 시 이 테이블을 그대로 참고하므로, 여기서 수정하면
    바로 다음 마케팅 콘텐츠 생성부터 반영된다(코드 수정 불필요).
    """
    return get_supabase().table("products").select("*").order("name").execute().data


@router.patch("/{name}", response_model=ProductOut)
def update_product(name: str, payload: ProductUpdate) -> dict:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    result = get_supabase().table("products").update(updates).eq("name", name).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="product not found")
    return result.data[0]
