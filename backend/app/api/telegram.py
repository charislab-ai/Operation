from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command

from app.config import settings
from app.db.supabase_client import get_supabase
from app.tools.telegram_bot import acknowledge_decision, get_bot, send_approval_request

router = APIRouter(prefix="/telegram", tags=["telegram"])

# 그래프를 resume해야 하는 target_type들 (finance_entry는 그래프 밖에서 직접 처리하므로 제외)
GRAPH_BASED_TARGET_TYPES = {"task_plan", "marketing_post", "dev_proposal"}


async def _handle_graph_resume(request: Request, supabase, approval_id: str, decision: str) -> None:
    approval_row = (
        supabase.table("approvals")
        .select("thread_id, telegram_msg_id, payload, target_type, interrupt_id")
        .eq("id", approval_id)
        .single()
        .execute()
    )
    thread_id = approval_row.data["thread_id"]
    original_message_id = approval_row.data.get("telegram_msg_id")
    original_payload = approval_row.data.get("payload")
    original_target_type = approval_row.data["target_type"]
    interrupt_id = approval_row.data.get("interrupt_id")

    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    # Goal형 병렬 실행에서는 같은 thread_id 안에 다른 부서의 interrupt가 동시에 더 남아있을 수 있어
    # interrupt_id로 "이 카드에 해당하는 interrupt만" 재개한다(나머지는 그대로 대기 유지).
    resume_value = {interrupt_id: {"decision": decision, "comment": ""}} if interrupt_id else {
        "decision": decision,
        "comment": "",
    }
    result = await graph.ainvoke(Command(resume=resume_value), config)

    supabase.table("approvals").update({"status": decision}).eq("id", approval_id).execute()

    if original_message_id and original_payload:
        await acknowledge_decision(int(original_message_id), original_target_type, original_payload, decision)

    # 보완(revision) 응답 이후 해당 Worker가 재실행되어 다시 승인 대기로 멈춘 경우, 새 승인 요청을 보낸다.
    # 이미 카드를 보낸 interrupt(다른 부서의 아직 처리 안 된 것 포함)는 건너뛰고 새로 생긴 것만 처리한다.
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return

    known_ids = {
        row["interrupt_id"]
        for row in supabase.table("approvals").select("interrupt_id").eq("thread_id", thread_id).execute().data
        if row.get("interrupt_id")
    }
    for interrupt_obj in interrupts:
        if interrupt_obj.id in known_ids:
            continue
        new_payload = interrupt_obj.value
        new_target_type = new_payload.get("type", "task_plan_approval").removesuffix("_approval")
        new_approval = (
            supabase.table("approvals")
            .insert(
                {
                    "target_type": new_target_type,
                    "thread_id": thread_id,
                    "status": "pending",
                    "payload": new_payload,
                    "interrupt_id": interrupt_obj.id,
                }
            )
            .execute()
        )
        new_approval_id = new_approval.data[0]["id"]
        message_id = await send_approval_request(new_approval_id, new_target_type, new_payload)
        supabase.table("approvals").update({"telegram_msg_id": str(message_id)}).eq(
            "id", new_approval_id
        ).execute()


async def _handle_finance_entry(supabase, approval_id: str, decision: str) -> None:
    approval_row = (
        supabase.table("approvals")
        .select("target_id, telegram_msg_id, payload")
        .eq("id", approval_id)
        .single()
        .execute()
    )
    target_id = approval_row.data["target_id"]
    original_message_id = approval_row.data.get("telegram_msg_id")
    original_payload = approval_row.data.get("payload")

    new_status = "confirmed" if decision == "approved" else "rejected"
    supabase.table("finance_entries").update({"status": new_status}).eq("id", target_id).execute()
    supabase.table("approvals").update({"status": decision}).eq("id", approval_id).execute()

    if original_message_id and original_payload:
        await acknowledge_decision(int(original_message_id), "finance_entry", original_payload, decision)


@router.post("/webhook")
async def telegram_webhook(request: Request) -> dict:
    # 실배포 후 setWebhook(secret_token=...)으로 등록하면 텔레그램이 매 요청에 이 헤더를 실어보낸다.
    # 값이 비어있으면(로컬 개발, webhook 미등록 상태) 검사를 건너뛴다.
    if settings.telegram_webhook_secret:
        incoming = request.headers.get("x-telegram-bot-api-secret-token")
        if incoming != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="invalid webhook secret")

    update = await request.json()
    callback_query = update.get("callback_query")
    if not callback_query:
        return {"ok": True}

    try:
        await get_bot().answer_callback_query(callback_query["id"])
    except Exception:
        # 오래된/중복/테스트용 콜백이면 Telegram이 응답을 거부할 수 있다 — 버튼 스피너만 못 없앨 뿐
        # 아래 승인 처리 로직 자체는 계속 진행해야 하므로 무시한다.
        pass

    parts = callback_query.get("data", "").split(":")
    if len(parts) != 3:
        return {"ok": True}
    target_type, approval_id, decision = parts

    supabase = get_supabase()
    if target_type in GRAPH_BASED_TARGET_TYPES:
        await _handle_graph_resume(request, supabase, approval_id, decision)
    elif target_type == "finance_entry":
        await _handle_finance_entry(supabase, approval_id, decision)

    return {"ok": True}
