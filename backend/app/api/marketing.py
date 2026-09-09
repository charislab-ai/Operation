import base64
import mimetypes
import re
import uuid

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/marketing", tags=["marketing"])

PRODUCT_ASSETS_BUCKET = "product-assets"

# 마케팅 벤치마킹 리포트 조회 - 클라우드 루틴이 하루 2회 GitHub에 직접 커밋하는 파일들을 읽는다.
# 배포된 백엔드 컨테이너의 파일시스템은 마지막 배포 시점 스냅샷이라 최신 리포트가 없을 수 있어,
# GitHub API로 실시간 조회한다(재배포 불필요).
GITHUB_API_BASE = "https://api.github.com"
BENCHMARKS_PATH = "docs/marketing_benchmarks"
_BENCHMARK_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-UTC\.md$")


def _github_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


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
    url = f"{GITHUB_API_BASE}/repos/{settings.github_repo}/contents/{BENCHMARKS_PATH}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_github_headers())
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API 오류: {resp.status_code}")

    items = []
    for entry in resp.json():
        name = entry.get("name", "")
        if not _BENCHMARK_FILENAME_RE.match(name):
            continue
        date_part = name[:10]
        time_part = name[11:15]
        items.append({"filename": name, "date": date_part, "time": f"{time_part[:2]}:{time_part[2:]} UTC"})
    items.sort(key=lambda x: x["filename"], reverse=True)
    return items


@router.get("/benchmarks/{filename}", response_model=BenchmarkDetail)
async def get_benchmark(filename: str) -> dict:
    if not _BENCHMARK_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="invalid filename")
    if not settings.github_token:
        raise HTTPException(status_code=503, detail="GITHUB_TOKEN이 설정되지 않았습니다")

    url = f"{GITHUB_API_BASE}/repos/{settings.github_repo}/contents/{BENCHMARKS_PATH}/{filename}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, headers=_github_headers())
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="not found")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API 오류: {resp.status_code}")

    data = resp.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return {"filename": filename, "content": content}
