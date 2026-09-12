from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.services.approvals import GRAPH_BASED_TARGET_TYPES, decide_finance_entry, resume_approval

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected", "revision"]
    comment: str | None = None


@router.post("/{approval_id}/decide")
async def decide_approval(approval_id: str, payload: ApprovalDecision, request: Request) -> dict:
    """업무 지시 웹 화면에서 승인/반려/보완을 처리한다 - 텔레그램 버튼과 완전히 동일한
    resume 경로를 재사용한다(app/services/approvals.py)."""
    supabase = get_supabase()
    row = supabase.table("approvals").select("status, target_type").eq("id", approval_id).single().execute()
    if not row.data:
        raise HTTPException(status_code=404, detail="approval not found")
    if row.data["status"] != "pending":
        raise HTTPException(status_code=409, detail="이미 처리된 승인 요청입니다")

    target_type = row.data["target_type"]
    if target_type == "finance_entry":
        if payload.decision not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="finance_entry는 승인/반려만 가능합니다")
        await decide_finance_entry(supabase, approval_id, payload.decision)
    elif target_type in GRAPH_BASED_TARGET_TYPES:
        await resume_approval(request.app.state.graph, supabase, approval_id, payload.decision, payload.comment or "")
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 승인 유형: {target_type}")

    return {"status": "ok"}
