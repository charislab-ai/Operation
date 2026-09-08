import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.tools.telegram_bot import send_approval_request

router = APIRouter(prefix="/directives", tags=["directives"])


class DirectiveCreate(BaseModel):
    text: str


class DirectiveOut(BaseModel):
    thread_id: str
    status: str


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


@router.post("", response_model=DirectiveOut)
async def create_directive(payload: DirectiveCreate, request: Request) -> dict:
    graph = request.app.state.graph
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # 업무 지시 카드 목록 화면이 항상 이 지시를 보여줄 수 있도록, 그래프 실행 전에 먼저 남긴다
    # (실행 도중 문제가 생겨도 "제출된 지시" 자체는 남아야 함).
    get_supabase().table("directives").insert(
        {"thread_id": thread_id, "ceo_directive": payload.text}
    ).execute()

    result = await graph.ainvoke({"ceo_directive": payload.text, "messages": []}, config)

    interrupts = result.get("__interrupt__")
    if not interrupts:
        return {"thread_id": thread_id, "status": "completed"}

    # Goal형 병렬 실행에서는 여러 부서가 동시에 승인을 기다릴 수 있어 interrupt가 여러 개 올 수 있다
    # (예: marketing_post_approval + dev_proposal_approval 동시). 각각 별도 카드로 보낸다.
    for interrupt_obj in interrupts:
        interrupt_payload = interrupt_obj.value
        # 각 노드가 만드는 payload의 "type"으로 어떤 종류의 승인인지 판별한다
        # (task_plan_approval → task_plan, marketing_post_approval → marketing_post).
        target_type = interrupt_payload.get("type", "task_plan_approval").removesuffix("_approval")

        approval = (
            get_supabase()
            .table("approvals")
            .insert(
                {
                    "target_type": target_type,
                    "thread_id": thread_id,
                    "status": "pending",
                    "payload": interrupt_payload,
                    "interrupt_id": interrupt_obj.id,
                }
            )
            .execute()
        )
        approval_id = approval.data[0]["id"]

        message_id = await send_approval_request(approval_id, target_type, interrupt_payload)
        get_supabase().table("approvals").update({"telegram_msg_id": str(message_id)}).eq(
            "id", approval_id
        ).execute()

    return {"thread_id": thread_id, "status": "pending_approval"}


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
    }
