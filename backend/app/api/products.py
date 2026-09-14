from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.tools.ai.image.mascot import MASCOT_BUCKET, ensure_mascot

router = APIRouter(prefix="/products", tags=["products"])


def _mascot_url(row: dict) -> str | None:
    path = row.get("mascot_asset_path")
    if not path:
        return None
    return get_supabase().storage.from_(MASCOT_BUCKET).get_public_url(path)


def _with_mascot_url(row: dict) -> dict:
    return {**row, "mascot_url": _mascot_url(row)}


class ProductOut(BaseModel):
    id: str
    name: str
    ios_url: str | None
    android_url: str | None
    brand_color: str | None
    description: str | None
    mascot_prompt: str | None = None
    mascot_url: str | None = None


class ProductUpdate(BaseModel):
    ios_url: str | None = None
    android_url: str | None = None
    brand_color: str | None = None
    description: str | None = None
    mascot_prompt: str | None = None


class ProductCreate(BaseModel):
    name: str
    ios_url: str | None = None
    android_url: str | None = None
    brand_color: str | None = None
    description: str | None = None


@router.get("", response_model=list[ProductOut])
def list_products() -> list[dict]:
    """앱관리 화면용 - 실제 출시된 앱 목록과 스토어 링크/브랜드 컬러/설명/인스타툰 마스코트.

    MarketingWorker가 카드뉴스 생성 시 이 테이블을 그대로 참고하므로, 여기서 수정하면
    바로 다음 마케팅 콘텐츠 생성부터 반영된다(코드 수정 불필요).
    """
    rows = get_supabase().table("products").select("*").order("name").execute().data
    return [_with_mascot_url(r) for r in rows]


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
    return _with_mascot_url(result.data[0])


@router.patch("/{name}", response_model=ProductOut)
def update_product(name: str, payload: ProductUpdate) -> dict:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    result = get_supabase().table("products").update(updates).eq("name", name).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="product not found")
    return _with_mascot_url(result.data[0])


@router.post("/{name}/mascot/regenerate", response_model=ProductOut)
async def regenerate_mascot(name: str) -> dict:
    """인스타툰용 마스코트 캐릭터를 (재)생성한다. 기존 마스코트가 있어도 강제로 새로 그린다 -
    CEO가 캐릭터 묘사(mascot_prompt)를 바꾼 뒤 미리보기를 다시 보고 싶을 때 사용."""
    result = get_supabase().table("products").select("*").eq("name", name).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="product not found")
    row = result.data[0]
    await ensure_mascot(row, force=True)
    refreshed = get_supabase().table("products").select("*").eq("name", name).execute().data[0]
    return _with_mascot_url(refreshed)
