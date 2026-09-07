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


@router.post("", response_model=DirectiveOut)
async def create_directive(payload: DirectiveCreate, request: Request) -> dict:
    graph = request.app.state.graph
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

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
