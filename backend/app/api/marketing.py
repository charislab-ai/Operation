import mimetypes
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db.supabase_client import get_supabase
from app.tools.github_benchmarks import fetch_benchmark_content, list_benchmark_filenames

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


class BenchmarkListItem(BaseModel):
    filename: str
    date: str
    time: str


class BenchmarkDetail(BaseModel):
    filename: str
    content: str


@router.get("/benchmarks", response_model=list[BenchmarkListItem])
async def list_benchmarks() -> list[dict]:
    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN이 설정되지 않았습니다")
    filenames = await list_benchmark_filenames()
    items = []
    for name in filenames:
        date_part = name[:10]
        time_part = name[11:15]
        items.append({"filename": name, "date": date_part, "time": f"{time_part[:2]}:{time_part[2:]} UTC"})
    return items


@router.get("/benchmarks/{filename}", response_model=BenchmarkDetail)
async def get_benchmark(filename: str) -> dict:
    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN이 설정되지 않았습니다")
    content = await fetch_benchmark_content(filename)
    if content is None:
        raise HTTPException(status_code=404, detail="not found")
    return {"filename": filename, "content": content}


class AutoScheduleOut(BaseModel):
    enabled: bool
    interval_hours: int
    products: list[str]
    last_run_at: str | None
    last_product: str | None


class AutoScheduleUpdate(BaseModel):
    enabled: bool | None = None
    interval_hours: int | None = None
    products: list[str] | None = None


@router.get("/auto-schedule", response_model=AutoScheduleOut)
def get_auto_schedule() -> dict:
    """정기 자동 발행 설정 조회 - 켜두면 CEO가 지시하지 않아도 주기적으로 콘텐츠를 만들어
    결재에 올린다(게시는 여전히 CEO 승인 후에만 이뤄짐)."""
    rows = get_supabase().table("marketing_auto_schedule").select("*").eq("id", 1).execute().data
    if not rows:
        return {"enabled": False, "interval_hours": 72, "products": [], "last_run_at": None, "last_product": None}
    return rows[0]


@router.patch("/auto-schedule", response_model=AutoScheduleOut)
def update_auto_schedule(payload: AutoScheduleUpdate) -> dict:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    if "interval_hours" in updates and updates["interval_hours"] < 1:
        raise HTTPException(status_code=400, detail="발행 주기는 1시간 이상이어야 합니다")
    result = get_supabase().table("marketing_auto_schedule").update(updates).eq("id", 1).execute()
    return result.data[0]


class AiBudgetOut(BaseModel):
    enabled: bool
    daily_image_limit: int
    daily_token_limit: int
    per_thread_image_limit: int
    used_images_today: int
    used_tokens_today: int


class AiBudgetUpdate(BaseModel):
    enabled: bool | None = None
    daily_image_limit: int | None = None
    daily_token_limit: int | None = None
    per_thread_image_limit: int | None = None


@router.get("/ai-budget", response_model=AiBudgetOut)
def get_ai_budget() -> dict:
    """AI 사용량 상한 + 오늘 사용량 - 버그로 크레딧이 폭주하는 걸 막는 안전장치 상태."""
    from app.services.budget import load_budget, usage_today

    budget = load_budget()
    used = usage_today()
    return {**budget, "used_images_today": used["images"], "used_tokens_today": used["tokens"]}


@router.patch("/ai-budget", response_model=AiBudgetOut)
def update_ai_budget(payload: AiBudgetUpdate) -> dict:
    from app.services.budget import usage_today

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    row = get_supabase().table("ai_budget").update(updates).eq("id", 1).execute().data[0]
    used = usage_today()
    return {**row, "used_images_today": used["images"], "used_tokens_today": used["tokens"]}


class LayoutOut(BaseModel):
    id: str
    name: str
    when_to_use: str
    spec: dict
    source: str | None
    enabled: bool
    times_used: int


@router.get("/layouts", response_model=list[LayoutOut])
def list_layouts() -> list[dict]:
    """벤치마킹으로 찾아내 기억하고 있는 카드 틀 목록 - 비주얼 디자이너가 여기서 골라 쓰거나
    여러 개를 조합해 새 틀을 만든다."""
    return get_supabase().table("layout_library").select("*").order("name").execute().data


@router.patch("/layouts/{layout_id}", response_model=LayoutOut)
def toggle_layout(layout_id: str, enabled: bool) -> dict:
    """마음에 안 드는 틀은 꺼둘 수 있다(끄면 디자이너가 후보에서 제외)."""
    result = get_supabase().table("layout_library").update({"enabled": enabled}).eq("id", layout_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="layout not found")
    return result.data[0]
