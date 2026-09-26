import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.db.checkpointer import delete_thread_checkpoint
from app.db.supabase_client import get_supabase
from app.graphs import task_registry
from app.services.directive_intake import (
    DIRECTIVE_MEDIA_BUCKET,
    UploadedMediaRef,
    create_directive_and_run,
    upload_one_media,
)
from app.tools.telegram_bot import acknowledge_decision

router = APIRouter(prefix="/directives", tags=["directives"])

# 개별 approval row의 status(pending/processing/approved/rejected/revision/cancelled)를
# 화면에 보여줄 지시 전체의 대표 상태로 정규화한다. approvals가 여러 부서(goal형 병렬 실행)에
# 걸쳐 있을 수 있어 "가장 최근에 생긴 approval의 상태"만 보면 다른 부서가 아직 pending인데
# "완료"로 보이는 등 실제와 어긋나는 문제가 실측으로 확인됐다 - 우선순위 기반으로 계산한다.
_STATUS_PRIORITY = ("processing", "pending")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _compute_status(graph, thread_id: str, approvals: list[dict], directive_row: dict) -> str:
    if directive_row.get("terminated_at"):
        return "terminated"
    if directive_row.get("paused_at"):
        return "paused"

    statuses = {a["status"] for a in approvals}
    # 실패 기록이 있는데 그 뒤로 다시 처리 중/대기 중인 게 없다면 "실패"로 보여준다 -
    # 예전엔 워커가 죽어도 "진행중"으로만 남아 CEO가 원인을 알 수 없었다.
    if directive_row.get("failed_at") and not ({"processing", "pending"} & statuses):
        return "failed"
    for priority in _STATUS_PRIORITY:
        if priority in statuses:
            return "in_progress" if priority == "processing" else "pending_approval"

    if not approvals:
        # 아직 첫 interrupt에 도달하지 못했을 수 있음(그래프가 여전히 실행 중) - 체크포인트로 확인.
        # approval이 있는 스레드가 대다수라 이 경로는 드물게만 타므로 성능 영향은 작다.
        try:
            snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            if snapshot.next:
                return "in_progress"
        except Exception:
            pass
        return "completed"

    latest = max(approvals, key=lambda a: a["created_at"])
    if latest["status"] == "rejected":
        return "rejected"
    if latest["status"] == "cancelled":
        return "terminated"
    if latest["status"] == "revision":
        # 정상 흐름이면 이 시점엔 이미 새 approval(pending/processing)이 생겨 위에서 걸러졌어야 함 -
        # 혹시 아직 안 생겼다면(레이스) "진행중"으로 보이는 게 "완료"보다 안전하다.
        return "in_progress"
    return "completed"


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
    status: str
    last_error: str | None = None
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
async def get_directive(thread_id: str, request: Request) -> dict:
    supabase = get_supabase()
    directive_row = (
        supabase.table("directives")
        .select("paused_at, terminated_at, failed_at, last_error")
        .eq("thread_id", thread_id)
        .limit(1)
        .execute()
    )
    if not directive_row.data:
        raise HTTPException(status_code=404, detail="directive not found")
    approvals = (
        supabase.table("approvals").select("status, created_at").eq("thread_id", thread_id).execute().data
    )
    status = await _compute_status(request.app.state.graph, thread_id, approvals, directive_row.data[0])
    return {"thread_id": thread_id, "status": status}


@router.patch("/{thread_id}", response_model=DirectiveOut)
async def update_directive(thread_id: str, payload: DirectiveUpdate, request: Request) -> dict:
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
    approvals = (
        supabase.table("approvals").select("status, created_at").eq("thread_id", thread_id).execute().data
    )
    status = await _compute_status(request.app.state.graph, thread_id, approvals, result.data[0])
    return {"thread_id": thread_id, "status": status}


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


@router.post("/{thread_id}/pause")
def pause_directive(thread_id: str) -> dict:
    """지금 실행 중인 백그라운드 처리가 있으면 취소하고, 지시를 "정지" 상태로 표시한다.
    이미 대기 중인 승인(pending)이 있으면 그건 그대로 남아있어(취소하지 않음) - CEO가 "재개"
    없이도 그 카드는 여전히 결정할 수 있다. 정지는 주로 "지금 도는 처리를 멈추고 싶다"는
    의도라 새로 생기는 처리만 막는다(POST /approvals/{id}/decide가 정지 중엔 409로 거부)."""
    task_registry.cancel(thread_id)
    supabase = get_supabase()
    result = supabase.table("directives").update({"paused_at": _now_iso()}).eq("thread_id", thread_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")
    return {"thread_id": thread_id, "status": "paused"}


@router.post("/{thread_id}/resume")
async def resume_directive(thread_id: str, request: Request) -> dict:
    """정지를 해제한다. 정지 당시 실행 중이던 처리가 취소돼 그래프가 체크포인트 중간에
    멈춰있을 수 있는 경우(대기 중인 approval이 하나도 없을 때만)에는 이어서 진행시킨다 -
    이미 대기 중인 approval이 있으면 그걸로 충분하니 그래프를 다시 건드리지 않는다."""
    supabase = get_supabase()
    result = (
        supabase.table("directives")
        .update({"paused_at": None, "failed_at": None, "last_error": None})
        .eq("thread_id", thread_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")

    open_approvals = (
        supabase.table("approvals")
        .select("id")
        .eq("thread_id", thread_id)
        .in_("status", ["pending", "processing"])
        .execute()
        .data
    )
    if not open_approvals:
        graph = request.app.state.graph
        config = {"configurable": {"thread_id": thread_id}}

        async def _continue() -> None:
            try:
                await graph.ainvoke(None, config)
            except Exception:
                pass

        task = asyncio.create_task(_continue())
        task_registry.register(thread_id, task)

    return {"thread_id": thread_id, "status": "resumed"}


@router.post("/{thread_id}/terminate")
async def terminate_directive(thread_id: str) -> dict:
    """강제 종료 - 실행 중인 처리를 취소하고, 열려있는(pending/processing) approval을 전부
    무효화(cancelled)한다. 정지와 달리 되돌릴 수 없다(재개 없음, 삭제만 가능)."""
    task_registry.cancel(thread_id)
    supabase = get_supabase()

    open_rows = (
        supabase.table("approvals")
        .select("id, telegram_msg_id, target_type, payload")
        .eq("thread_id", thread_id)
        .in_("status", ["pending", "processing"])
        .execute()
        .data
    )
    for row in open_rows:
        supabase.table("approvals").update({"status": "cancelled"}).eq("id", row["id"]).execute()
        if row.get("telegram_msg_id") and row.get("payload"):
            try:
                await acknowledge_decision(
                    int(row["telegram_msg_id"]), row["target_type"], row["payload"], "cancelled"
                )
            except Exception:
                pass

    result = (
        supabase.table("directives")
        .update({"terminated_at": _now_iso(), "paused_at": None})
        .eq("thread_id", thread_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")
    return {"thread_id": thread_id, "status": "terminated"}


@router.delete("/{thread_id}")
async def delete_directive(thread_id: str) -> dict:
    """업무 지시를 완전히 삭제한다 - approvals/agent_runs/ai_usage_log/첨부 미디어(스토리지 파일
    포함)/LangGraph 체크포인트까지 전부 지운다. 되돌릴 수 없다."""
    task_registry.cancel(thread_id)
    supabase = get_supabase()

    media_rows = (
        supabase.table("directive_media").select("storage_path").eq("thread_id", thread_id).execute().data
    )
    if media_rows:
        supabase.storage.from_(DIRECTIVE_MEDIA_BUCKET).remove([m["storage_path"] for m in media_rows])
        supabase.table("directive_media").delete().eq("thread_id", thread_id).execute()

    supabase.table("ai_usage_log").delete().eq("thread_id", thread_id).execute()
    supabase.table("agent_runs").delete().eq("thread_id", thread_id).execute()
    supabase.table("approvals").delete().eq("thread_id", thread_id).execute()
    result = supabase.table("directives").delete().eq("thread_id", thread_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="directive not found")

    try:
        await delete_thread_checkpoint(thread_id)
    except Exception:
        pass

    return {"status": "deleted"}


@router.get("", response_model=list[DirectiveListItem])
async def list_directives(request: Request, limit: int = 100) -> list[dict]:
    """업무 지시 카드 목록 화면용 - 지금까지 제출된 모든 지시 + 각각의 대표 상태(우선순위 기반
    계산, _compute_status 참고 - "가장 최근에 생긴 approval" 하나만 보면 다른 부서가 아직
    처리 중인데 완료로 보이는 등 실제와 어긋나는 문제가 있었다)."""
    supabase = get_supabase()
    directives = (
        supabase.table("directives")
        .select("thread_id, ceo_directive, created_at, paused_at, terminated_at, failed_at, last_error")
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
        .execute()
        .data
        if thread_ids
        else []
    )
    approvals_by_thread: dict[str, list[dict]] = {}
    for a in approvals:
        approvals_by_thread.setdefault(a["thread_id"], []).append(a)

    graph = request.app.state.graph
    statuses = await asyncio.gather(
        *(_compute_status(graph, d["thread_id"], approvals_by_thread.get(d["thread_id"], []), d) for d in directives)
    )
    return [
        {"thread_id": d["thread_id"], "ceo_directive": d["ceo_directive"], "created_at": d["created_at"], "latest_status": status}
        for d, status in zip(directives, statuses)
    ]


@router.get("/{thread_id}/detail", response_model=DirectiveDetailOut)
async def get_directive_detail(thread_id: str, request: Request) -> dict:
    """업무 지시 상세 화면용 - 전체 워크플로우/산출물/결정사항/AI 사용량을 한 번에 모아 반환."""
    supabase = get_supabase()
    directive_row = (
        supabase.table("directives")
        .select("thread_id, ceo_directive, created_at, paused_at, terminated_at, failed_at, last_error")
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
    status = await _compute_status(graph, thread_id, approvals, directive)
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
        "status": status,
        "last_error": directive.get("last_error"),
        "active_departments": state_values.get("active_departments", []),
        "worker_briefs": state_values.get("worker_briefs", {}),
        "decisions": state_values.get("decisions", {}),
        "revision_notes": state_values.get("revision_notes", {}),
        "outputs": {
            "marketing_post": state_values.get("marketing_post"),
            "dev_proposal": state_values.get("dev_proposal"),
        },
        "approvals": approvals,
        "agent_runs": agent_runs,
        "ai_usage": ai_usage,
        "media": media,
    }
