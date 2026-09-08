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


class ProductCreate(BaseModel):
    name: str
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


@router.post("", response_model=ProductOut)
def create_product(payload: ProductCreate) -> dict:
    """새 앱을 앱관리 화면에서 CEO가 직접 등록한다(자동 등록 없음 - 오타/중복 이름으로
    쓰레기 데이터가 쌓이는 걸 막기 위해 명시적으로 CEO가 등록해야만 products에 들어감)."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="앱 이름을 입력하세요")
    existing = get_supabase().table("products").select("id").eq("name", name).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="이미 등록된 이름입니다")
    row = {**payload.model_dump(), "name": name}
    result = get_supabase().table("products").insert(row).execute()
    return result.data[0]


@router.patch("/{name}", response_model=ProductOut)
def update_product(name: str, payload: ProductUpdate) -> dict:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    result = get_supabase().table("products").update(updates).eq("name", name).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="product not found")
    return result.data[0]
