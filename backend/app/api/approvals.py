import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.graphs import task_registry
from app.services.approvals import GRAPH_BASED_TARGET_TYPES, claim_approval, decide_finance_entry, resume_approval

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected", "revision"]
    comment: str | None = None


@router.post("/{approval_id}/decide")
async def decide_approval(approval_id: str, payload: ApprovalDecision, request: Request) -> dict:
    """업무 지시 웹 화면에서 승인/반려/보완을 처리한다 - 텔레그램 버튼과 완전히 동일한
    resume 경로를 재사용한다(app/services/approvals.py).

    claim_approval로 원자적으로 선점한 뒤 즉시 응답을 돌려주고, 실제 처리(그래프 재개 -
    마케팅 보완이면 LLM+이미지 생성을 통째로 다시 돌아 몇 분씩 걸림)는 백그라운드로 넘긴다 -
    브라우저가 그동안 요청을 붙들고 있지 않아야 화면에서 실시간으로 진행 상황을 보여줄 수 있다
    (실측 확인된 문제: 예전엔 이 호출이 몇 분씩 안 끝나서 화면이 멈춰 있었음).
    """
    supabase = get_supabase()
    row = supabase.table("approvals").select("target_type, thread_id").eq("id", approval_id).single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="approval not found")
    target_type = row.data["target_type"]
    thread_id = row.data.get("thread_id")

    if target_type == "finance_entry" and payload.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="finance_entry는 승인/반려만 가능합니다")
    if target_type not in GRAPH_BASED_TARGET_TYPES and target_type != "finance_entry":
        raise HTTPException(status_code=400, detail=f"지원하지 않는 승인 유형: {target_type}")

    if thread_id:
        directive_row = (
            supabase.table("directives").select("paused_at, terminated_at").eq("thread_id", thread_id).execute()
        )
        if directive_row.data and directive_row.data[0].get("terminated_at"):
            raise HTTPException(status_code=409, detail="강제 종료된 업무 지시입니다")
        if directive_row.data and directive_row.data[0].get("paused_at"):
            raise HTTPException(status_code=409, detail="정지된 업무 지시입니다 - 먼저 재개하세요")

    claimed = await claim_approval(supabase, approval_id)
    if not claimed:
        raise HTTPException(status_code=409, detail="이미 처리된 승인 요청입니다")

    if target_type == "finance_entry":
        await decide_finance_entry(supabase, approval_id, payload.decision)
        return {"status": payload.decision}

    async def _run() -> None:
        try:
            await resume_approval(
                request.app.state.graph, supabase, approval_id, payload.decision, payload.comment or ""
            )
        except Exception:
            pass  # 백그라운드 태스크 - 예외를 삼켜서 미처리 태스크 경고로 그치게 함(TODO: 로깅)

    task = asyncio.create_task(_run())
    if thread_id:
        task_registry.register(thread_id, task)
    return {"status": "processing"}
