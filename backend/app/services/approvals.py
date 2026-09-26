"""승인(approvals) 처리의 핵심 로직 - 텔레그램 웹훅과 웹 "업무 지시" 화면 양쪽에서
동일하게 호출한다(호출부가 request(텔레그램)냐 REST 엔드포인트(웹)냐만 다를 뿐, 실제로
그래프를 재개하고 새 interrupt를 카드로 만들어 보내는 로직은 완전히 같아야 함)."""

from langgraph.types import Command

from app.services.failures import record_graph_failure
from app.tools.telegram_bot import acknowledge_decision, send_approval_request

# 그래프를 resume해야 하는 target_type들 (finance_entry는 그래프 밖에서 직접 처리하므로 제외)
GRAPH_BASED_TARGET_TYPES = {"task_plan", "marketing_post", "dev_proposal"}


async def claim_approval(supabase, approval_id: str) -> dict | None:
    """이 approval의 처리를 "선점"한다 - status를 pending -> processing으로 원자적으로
    전환하고, 실제로 이 호출이 전환에 성공했을 때만 그 row를 반환한다.

    Why: 마케팅 보완 같은 처리는 LLM+이미지 생성 파이프라인 전체를 다시 돌아서 몇 분씩
    걸리는데, 그동안 텔레그램 버튼이 살아있거나 웹훅이 중복 전달되면 같은 결정이 두 번
    처리될 수 있었다(실측 확인 - 반려 이후에도 겹쳐 실행되던 중복 처리가 새 승인을 계속
    만들어냈음). status 컬럼을 원자적 락으로 써서 두 번째 호출은 조용히 무시하게 만든다.
    """
    result = (
        supabase.table("approvals")
        .update({"status": "processing"})
        .eq("id", approval_id)
        .eq("status", "pending")
        .execute()
    )
    return result.data[0] if result.data else None


async def resume_approval(graph, supabase, approval_id: str, decision: str, comment: str = "") -> None:
    """승인/반려/보완의 실제 처리 - claim_approval로 선점에 성공한 뒤에만 호출해야 한다.
    LangGraph를 resume하고, 결과로 새 interrupt가 생기면(보완 후 해당 Worker가 재실행되어
    다시 멈춘 경우 등) 새 승인 카드를 만들어 보낸다. 오래 걸릴 수 있으므로 호출부가 백그라운드
    태스크로 실행해야 한다(응답을 기다리게 하면 안 됨).
    """
    approval_row = (
        supabase.table("approvals")
        .select("thread_id, telegram_msg_id, payload, target_type, interrupt_id, edited_at")
        .eq("id", approval_id)
        .single()
        .execute()
    )
    thread_id = approval_row.data["thread_id"]
    original_message_id = approval_row.data.get("telegram_msg_id")
    original_payload = approval_row.data.get("payload")
    original_target_type = approval_row.data["target_type"]
    interrupt_id = approval_row.data.get("interrupt_id")

    config = {"configurable": {"thread_id": thread_id}}
    # Goal형 병렬 실행에서는 같은 thread_id 안에 다른 부서의 interrupt가 동시에 더 남아있을 수 있어
    # interrupt_id로 "이 카드에 해당하는 interrupt만" 재개한다(나머지는 그대로 대기 유지).
    decision_payload: dict = {"decision": decision, "comment": comment}
    # 슬라이드 편집기로 고친 카드가 있으면(approvals.payload에 덮어써 둠) 그 편집본을 함께
    # 넘겨 승인 노드가 marketing_post를 교체하게 한다 - 안 넘기면 AI 원본이 게시돼버린다.
    if approval_row.data.get("edited_at") and original_target_type == "marketing_post" and original_payload:
        decision_payload["edited_post"] = {k: v for k, v in original_payload.items() if k != "type"}
    resume_value = {interrupt_id: decision_payload} if interrupt_id else decision_payload
    try:
        result = await graph.ainvoke(Command(resume=resume_value), config)
    except Exception as exc:
        # 백그라운드에서 도는 경로라 예외가 어디에도 안 보이고 승인은 processing으로 멈춰버린다 -
        # 기록/알림하고 승인을 pending으로 되돌려 CEO가 다시 결정할 수 있게 한다.
        await record_graph_failure(thread_id, exc, approval_id=approval_id)
        return

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


async def decide_finance_entry(supabase, approval_id: str, decision: str) -> None:
    """finance_entry는 LangGraph 밖에서 처리된다(그래프에 진입한 적 없는 영수증 승인) -
    approved|rejected만 유효(보완 버튼 자체가 없음)."""
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
