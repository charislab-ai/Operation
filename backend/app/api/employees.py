"""직원 명단 - 각 AI 에이전트를 직원으로 보여주고, CEO가 이름을 지어주고 입사/대기를 정한다.

이름은 단순 표시용이 아니다: CEO가 지시문에서 그 이름을 부르면 해당 직원만 "나에게 내려온
지시"로 받아들이고 나머지는 기존 방향을 유지한다(app/graphs/supervisor.py, _marketing_shared.py).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/employees", tags=["employees"])

_ACTIVE_WINDOW = timedelta(minutes=5)
_STATS_WINDOW_DAYS = 7


class EmployeeOut(BaseModel):
    id: str
    agent_key: str
    name: str
    title: str
    rank: str
    department: str
    responsibilities: str
    status: str  # active | onboarding | leave
    sort_order: int
    working: bool  # 지금 업무 중인지(진행 중인 run이 있는지)
    current_task: str | None  # 지금/마지막으로 하던 일 요약
    last_active_at: str | None
    runs_7d: int  # 최근 7일 처리 건수
    tokens_7d: int  # 최근 7일 사용 토큰


class EmployeeUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    rank: str | None = None
    responsibilities: str | None = None
    status: str | None = None


def _summarize(run: dict) -> str | None:
    """마지막 run의 입력에서 "무슨 일을 하고 있었는지" 한 줄을 뽑는다."""
    payload = run.get("input") or {}
    if not isinstance(payload, dict):
        return None
    for key in ("ceo_directive", "product", "slide_topics", "slides"):
        value = payload.get(key)
        if value:
            text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            return text[:80]
    return None


@router.get("", response_model=list[EmployeeOut])
def list_employees() -> list[dict]:
    """직원 명단 + 각자의 현재 업무 상태. 화면(직원 탭)에서 그대로 카드로 그린다."""
    supabase = get_supabase()
    employees = supabase.table("employees").select("*").order("sort_order").execute().data

    since = (datetime.now(timezone.utc) - timedelta(days=_STATS_WINDOW_DAYS)).isoformat()
    runs = (
        supabase.table("agent_runs")
        .select("agent_name, input, started_at, finished_at")
        .gte("started_at", since)
        .order("started_at", desc=True)
        .execute()
        .data
    )
    usage = (
        supabase.table("ai_usage_log")
        .select("agent_name, total_tokens, created_at")
        .gte("created_at", since)
        .execute()
        .data
    )

    runs_by_agent: dict[str, list[dict]] = {}
    for r in runs:
        runs_by_agent.setdefault(r.get("agent_name") or "", []).append(r)
    tokens_by_agent: dict[str, int] = {}
    for u in usage:
        tokens_by_agent[u.get("agent_name") or ""] = tokens_by_agent.get(u.get("agent_name") or "", 0) + (
            u.get("total_tokens") or 0
        )

    now = datetime.now(timezone.utc)
    out = []
    for e in employees:
        agent_runs = runs_by_agent.get(e.get("run_agent_name") or "", [])
        latest = agent_runs[0] if agent_runs else None
        working = False
        if latest and not latest.get("finished_at"):
            started = datetime.fromisoformat(latest["started_at"].replace("Z", "+00:00"))
            working = now - started < _ACTIVE_WINDOW
        out.append(
            {
                **e,
                "working": working,
                "current_task": _summarize(latest) if latest else None,
                "last_active_at": latest["started_at"] if latest else None,
                "runs_7d": len(agent_runs),
                "tokens_7d": tokens_by_agent.get(e.get("run_agent_name") or "", 0),
            }
        )
    return out


@router.patch("/{agent_key}", response_model=EmployeeOut)
def update_employee(agent_key: str, payload: EmployeeUpdate) -> dict:
    """CEO가 직원 이름을 지어주거나(이름으로 부르면 그 직원이 알아듣는다), 입사 예정 직원을
    입사시키거나(status=active), 잠시 대기시킨다(status=leave)."""
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다")
    if "status" in updates and updates["status"] not in ("active", "onboarding", "leave"):
        raise HTTPException(status_code=400, detail="상태 값이 올바르지 않습니다")
    if "name" in updates:
        name = updates["name"].strip()
        if len(name) < 2:
            # 한 글자 이름은 지시문에서 오탐이 너무 많아(우연히 포함되는 글자) 지목 라우팅이 망가진다.
            raise HTTPException(status_code=400, detail="이름은 2글자 이상으로 지어주세요")
        others = get_supabase().table("employees").select("agent_key").eq("name", name).execute().data
        if any(o["agent_key"] != agent_key for o in others):
            raise HTTPException(status_code=409, detail="같은 이름의 직원이 이미 있습니다")
        updates["name"] = name

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = get_supabase().table("employees").update(updates).eq("agent_key", agent_key).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="employee not found")

    # 이름/상태가 바뀌면 지목 라우팅이 바로 새 이름을 쓰도록 캐시를 비운다.
    from app.graphs.workers._marketing_shared import fetch_employees

    fetch_employees(force=True)
    return list_employees_one(agent_key)


def list_employees_one(agent_key: str) -> dict:
    return next(e for e in list_employees() if e["agent_key"] == agent_key)
