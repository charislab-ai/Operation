import base64
import mimetypes
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db.supabase_client import get_supabase
from app.services.card_render import brand_color_of, fetch_image_bytes, render_slide
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


# ---------------------------------------------------------------------------
# 슬라이드 편집기 - 승인 전에 CEO가 카드의 문구/틀을 직접 고쳐서 바로 다시 그려본다.
# Why: 지금까지는 AI가 만든 결과를 "승인/보완/반려" 셋 중 하나로만 다룰 수 있었고, 헤드라인
# 한 줄이나 틀만 바꾸고 싶어도 보완을 걸어 파이프라인 전체(LLM+이미지 생성)를 다시 돌려야 했다
# (몇 분 + 이미지 생성 비용). 카드 합성에 필요한 원본 사진을 slides[].source_image_url로
# 보관해두었으므로, 문구/틀 수정은 AI 호출 없이 PIL 재합성만으로 끝난다(비용 0, 수 초).
# ---------------------------------------------------------------------------


class SlideRenderIn(BaseModel):
    headline: str
    subtext: str = ""
    layout_name: str = ""
    layout_spec: dict = {}
    source_image_url: str | None = None
    image_prompt: str = ""  # 사진 재생성용 지시문 - 편집 저장 시 함께 보관한다


class PreviewIn(SlideRenderIn):
    product: str
    page_label: str | None = None
    format: str = "card_news"


@router.post("/render-preview")
async def render_preview(payload: PreviewIn) -> dict:
    """문구/틀을 바꾼 카드 한 장을 AI 호출 없이 즉시 다시 그려 미리보기로 돌려준다(비용 0).
    프론트 편집기가 입력이 바뀔 때마다 호출하므로 절대 AI를 부르지 않는다."""
    photo = await fetch_image_bytes(payload.source_image_url)
    image = render_slide(
        payload.model_dump(),
        payload.product,
        payload.page_label,
        brand_color_of(payload.product),
        payload.format,
        photo,
    )
    return {"image_data_url": "data:image/png;base64," + base64.b64encode(image).decode()}


class PostEditIn(BaseModel):
    caption: str | None = None
    slides: list[SlideRenderIn]


@router.patch("/posts/{approval_id}")
async def edit_marketing_post(approval_id: str, payload: PostEditIn) -> dict:
    """결재 대기 중인 카드뉴스/인스타툰의 문구·틀·캡션을 확정 저장한다.

    편집 결과는 approvals.payload(= marketing_post와 같은 모양)에 덮어쓰고 edited_at을 찍는다.
    이후 CEO가 승인하면 resume_approval이 이 payload를 edited_post로 넘겨 그래프 상태의
    marketing_post를 교체하므로(app/graphs/human_approval.py), 실제 게시에도 편집본이 나간다.
    """
    from app.tools.ai.image.storage import upload_marketing_image

    supabase = get_supabase()
    rows = (
        supabase.table("approvals")
        .select("id, status, target_type, payload")
        .eq("id", approval_id)
        .execute()
        .data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="approval not found")
    row = rows[0]
    if row["target_type"] != "marketing_post":
        raise HTTPException(status_code=400, detail="카드뉴스 결재 카드만 편집할 수 있습니다")
    if row["status"] != "pending":
        # processing이면 이미 승인/보완 처리가 돌고 있다 - 그 위에 편집을 얹으면 어느 쪽이
        # 최종본인지 알 수 없게 되므로 막는다(중복 처리 방지 원칙과 동일).
        raise HTTPException(status_code=409, detail="이미 결재가 진행됐거나 처리 중이라 편집할 수 없습니다")

    post = dict(row["payload"] or {})
    slides = list(post.get("slides") or [])
    if len(payload.slides) != len(slides):
        raise HTTPException(
            status_code=400, detail=f"슬라이드 개수가 맞지 않습니다(현재 {len(slides)}장)"
        )

    product = post.get("product") or ""
    fmt = post.get("format", "card_news")
    brand = brand_color_of(product)
    total = len(slides)

    new_slides: list[dict] = []
    image_urls: list[str] = []
    for i, (existing, edit) in enumerate(zip(slides, payload.slides)):
        # 비워서 보낸 값은 "안 바꿈"으로 보고 기존 값을 유지한다. 단 헤드라인/보조문구는
        # 빈 문자열(= 지우기)도 유효한 편집이라 항상 그대로 반영한다.
        merged = dict(existing)
        merged["headline"] = edit.headline
        merged["subtext"] = edit.subtext
        for key in ("layout_name", "layout_spec", "source_image_url", "image_prompt"):
            value = getattr(edit, key)
            if value:
                merged[key] = value
        needs_photo = fmt == "instatoon" or (merged.get("layout_spec") or {}).get("photo_style", "full") != "none"
        if needs_photo and not merged.get("source_image_url"):
            # 편집기 도입(source_image_url 보관) 이전에 만들어진 카드 - 원본 사진이 없어서 다시
            # 합성하면 사진이 통째로 사라진다. 조용히 망가뜨리지 않고 막고, 사진 재생성을 안내한다.
            raise HTTPException(
                status_code=400,
                detail=f"{i + 1}번째 장은 편집기 도입 전에 만들어져 원본 사진이 없습니다 - "
                "'사진만 다시 생성'을 먼저 눌러주세요",
            )
        photo = await fetch_image_bytes(merged.get("source_image_url"))
        card = render_slide(merged, product, f"{i + 1}/{total}", brand, fmt, photo)
        image_urls.append(upload_marketing_image(card))
        new_slides.append(merged)

    post["slides"] = new_slides
    post["image_urls"] = image_urls
    if payload.caption is not None:
        post["caption"] = payload.caption

    supabase.table("approvals").update(
        {"payload": post, "edited_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", approval_id).eq("status", "pending").execute()
    return post


class RegeneratePhotoIn(BaseModel):
    image_prompt: str
    thread_id: str | None = None


@router.post("/regenerate-photo")
async def regenerate_photo(payload: RegeneratePhotoIn) -> dict:
    """슬라이드의 사진만 AI로 다시 생성한다 - 유료(이미지 1장 비용)라 CEO가 버튼을 직접
    눌렀을 때만 돈다. 문구/틀 수정(render-preview)은 이 경로를 타지 않는다."""
    from app.services.budget import BudgetExceeded
    from app.tools.ai.image import get_image_gen
    from app.tools.ai.image.storage import upload_marketing_image

    if not payload.image_prompt.strip():
        raise HTTPException(status_code=400, detail="사진 지시문을 입력해주세요")
    try:
        image = await get_image_gen().generate_bytes(
            payload.image_prompt, thread_id=payload.thread_id, agent_name="SlideEditor"
        )
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        from app.services.failures import describe_error

        raise HTTPException(status_code=502, detail=describe_error(exc)) from exc
    return {"source_image_url": upload_marketing_image(image)}
