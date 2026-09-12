from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.services.directive_intake import (
    DIRECTIVE_MEDIA_BUCKET,
    UploadedMediaRef,
    create_directive_and_run,
    upload_one_media,
)

router = APIRouter(prefix="/directives", tags=["directives"])


class DirectiveOut(BaseModel):
    thread_id: str
    status: str


class DirectiveUpdate(BaseModel):
    ceo_directive: str


class DirectiveMediaOut(BaseModel):
    id: str
    media_type: str
    url: str
    caption: str | None


class DirectiveMediaUpdate(BaseModel):
    caption: str


class DirectiveListItem(BaseModel):
    thread_id: str
    ceo_directive: str
    created_at: str
    latest_status: str


class AiUsageByAgent(BaseModel):
    agent_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    image_count: int
    cost_usd: float | None


class AiUsageSummary(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_image_count: int
    total_cost_usd: float | None
    by_agent: list[AiUsageByAgent]


class DirectiveDetailOut(BaseModel):
    thread_id: str
    ceo_directive: str
    created_at: str
    active_departments: list[str]
    worker_briefs: dict[str, str]
    decisions: dict[str, str]
    revision_notes: dict[str, str]
    outputs: dict
    approvals: list[dict]
    agent_runs: list[dict]
    ai_usage: AiUsageSummary
    media: list[DirectiveMediaOut]


@router.post("", response_model=DirectiveOut)
async def create_directive(
    request: Request,
    text: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict:
    """CEO 지시 제출 - 텍스트뿐 아니라 이미지/영상도 함께 첨부할 수 있다(멀티파트).
    실제 생성 로직은 텔레그램 "/지시" 명령과 공유한다(app/services/directive_intake.py)."""
    graph = request.app.state.graph
    media = [
        UploadedMediaRef(filename=f.filename, content=await f.read(), content_type=f.content_type)
        for f in files
    ]
    return await create_directive_and_run(graph, text, media)


@router.get("/{thread_id}", response_model=DirectiveOut)
def get_directive(thread_id: str) -> dict:
    result = (
        get_supabase()
        .table("approvals")
        .select("status")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")
    return {"thread_id": thread_id, "status": result.data[0]["status"]}


@router.patch("/{thread_id}", response_model=DirectiveOut)
def update_directive(thread_id: str, payload: DirectiveUpdate) -> dict:
    """지시 내용을 수정한다 - 기록만 바꿀 뿐 그래프/워커에는 아무 영향이 없다(의도적).
    실제로 다시 작업시키려면 승인/반려/보완(POST /approvals/{id}/decide) 경로를 쓴다."""
    supabase = get_supabase()
    result = (
        supabase.table("directives")
        .update({"ceo_directive": payload.ceo_directive})
        .eq("thread_id", thread_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")
    latest_status = (
        supabase.table("approvals")
        .select("status")
        .eq("thread_id", thread_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return {"thread_id": thread_id, "status": latest_status[0]["status"] if latest_status else "completed"}


@router.post("/{thread_id}/media", response_model=DirectiveMediaOut)
async def add_directive_media(
    thread_id: str, file: UploadFile = File(...), caption: str | None = Form(None)
) -> dict:
    supabase = get_supabase()
    content = await file.read()
    media_ref = UploadedMediaRef(
        filename=file.filename, content=content, content_type=file.content_type, caption=caption
    )
    return upload_one_media(supabase, thread_id, media_ref)


@router.patch("/{thread_id}/media/{media_id}", response_model=DirectiveMediaOut)
def update_directive_media(thread_id: str, media_id: str, payload: DirectiveMediaUpdate) -> dict:
    supabase = get_supabase()
    result = (
        supabase.table("directive_media").update({"caption": payload.caption}).eq("id", media_id).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="media not found")
    row = result.data[0]
    url = supabase.storage.from_(DIRECTIVE_MEDIA_BUCKET).get_public_url(row["storage_path"])
    return {"id": row["id"], "media_type": row["media_type"], "url": url, "caption": row["caption"]}


@router.delete("/{thread_id}/media/{media_id}")
def delete_directive_media(thread_id: str, media_id: str) -> dict:
    supabase = get_supabase()
    row = supabase.table("directive_media").select("storage_path").eq("id", media_id).execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="media not found")
    storage_path = row.data[0]["storage_path"]
    supabase.table("directive_media").delete().eq("id", media_id).execute()
    supabase.storage.from_(DIRECTIVE_MEDIA_BUCKET).remove([storage_path])
    return {"status": "deleted"}


@router.get("", response_model=list[DirectiveListItem])
def list_directives(limit: int = 100) -> list[dict]:
    """업무 지시 카드 목록 화면용 - 지금까지 제출된 모든 지시 + 각각의 최신 상태."""
    supabase = get_supabase()
    directives = (
        supabase.table("directives")
        .select("thread_id, ceo_directive, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    thread_ids = [d["thread_id"] for d in directives]
    approvals = (
        supabase.table("approvals")
        .select("thread_id, status, created_at")
        .in_("thread_id", thread_ids)
        .order("created_at", desc=True)
        .execute()
        .data
        if thread_ids
        else []
    )
    latest_status: dict[str, str] = {}
    for a in approvals:  # 이미 최신순 정렬 - thread_id별로 처음 만난 값이 최신 상태
        latest_status.setdefault(a["thread_id"], a["status"])

    return [
        {**d, "latest_status": latest_status.get(d["thread_id"], "completed")} for d in directives
    ]


@router.get("/{thread_id}/detail", response_model=DirectiveDetailOut)
async def get_directive_detail(thread_id: str, request: Request) -> dict:
    """업무 지시 상세 화면용 - 전체 워크플로우/산출물/결정사항/AI 사용량을 한 번에 모아 반환."""
    supabase = get_supabase()
    directive_row = (
        supabase.table("directives")
        .select("thread_id, ceo_directive, created_at")
        .eq("thread_id", thread_id)
        .limit(1)
        .execute()
    )
    if not directive_row.data:
        raise HTTPException(status_code=404, detail="directive not found")
    directive = directive_row.data[0]

    # 산출물/부서배정/결정사항은 새 테이블 없이 LangGraph 체크포인트의 현재 상태를 그대로 노출한다
    graph = request.app.state.graph
    snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    state_values = snapshot.values or {}

    approvals = (
        supabase.table("approvals")
        .select("id, target_type, status, payload, created_at, awaiting_comment")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
        .data
    )
    agent_runs = (
        supabase.table("agent_runs")
        .select("id, agent_name, input, output, started_at, finished_at")
        .eq("thread_id", thread_id)
        .order("started_at")
        .execute()
        .data
    )
    usage_rows = (
        supabase.table("ai_usage_log")
        .select("agent_name, input_tokens, output_tokens, total_tokens, image_count, cost_usd")
        .eq("thread_id", thread_id)
        .execute()
        .data
    )

    by_agent: dict[str, dict] = {}
    total_cost: float | None = None
    for row in usage_rows:
        agent = row.get("agent_name") or "unknown"
        bucket = by_agent.setdefault(
            agent,
            {
                "agent_name": agent,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "image_count": 0,
                "cost_usd": None,
            },
        )
        bucket["input_tokens"] += row.get("input_tokens") or 0
        bucket["output_tokens"] += row.get("output_tokens") or 0
        bucket["total_tokens"] += row.get("total_tokens") or 0
        bucket["image_count"] += row.get("image_count") or 0
        if row.get("cost_usd") is not None:
            bucket["cost_usd"] = (bucket["cost_usd"] or 0) + row["cost_usd"]
            total_cost = (total_cost or 0) + row["cost_usd"]

    ai_usage = {
        "total_input_tokens": sum(b["input_tokens"] for b in by_agent.values()),
        "total_output_tokens": sum(b["output_tokens"] for b in by_agent.values()),
        "total_tokens": sum(b["total_tokens"] for b in by_agent.values()),
        "total_image_count": sum(b["image_count"] for b in by_agent.values()),
        # 실비용 데이터가 하나도 없으면 None(0으로 지어내지 않음)
        "total_cost_usd": total_cost,
        "by_agent": list(by_agent.values()),
    }

    media_rows = (
        supabase.table("directive_media")
        .select("id, storage_path, media_type, caption")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
        .data
    )
    media_bucket = supabase.storage.from_(DIRECTIVE_MEDIA_BUCKET)
    media = [
        {
            "id": m["id"],
            "media_type": m["media_type"],
            "caption": m["caption"],
            "url": media_bucket.get_public_url(m["storage_path"]),
        }
        for m in media_rows
    ]

    return {
        "thread_id": thread_id,
        "ceo_directive": directive["ceo_directive"],
        "created_at": directive["created_at"],
        "active_departments": state_values.get("active_departments", []),
        "worker_briefs": state_values.get("worker_briefs", {}),
        "decisions": state_values.get("decisions", {}),
        "revision_notes": state_values.get("revision_notes", {}),
        "outputs": {
            "biz_plan": state_values.get("biz_plan"),
            "wbs_plan": state_values.get("wbs_plan"),
            "marketing_post": state_values.get("marketing_post"),
            "dev_proposal": state_values.get("dev_proposal"),
        },
        "approvals": approvals,
        "agent_runs": agent_runs,
        "ai_usage": ai_usage,
        "media": media,
    }
