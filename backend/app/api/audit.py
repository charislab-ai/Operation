from fastapi import APIRouter

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/log")
def audit_log(limit: int = 50) -> list[dict]:
    supabase = get_supabase()

    runs = (
        supabase.table("agent_runs")
        .select("id, agent_name, input, output, started_at, finished_at")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )
    approvals = (
        supabase.table("approvals")
        .select("id, target_type, status, thread_id, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )

    entries = [
        {
            "kind": "agent_run",
            "timestamp": run["started_at"],
            "agent_name": run["agent_name"],
            "finished_at": run["finished_at"],
            "input": run["input"],
            "output": run["output"],
        }
        for run in runs
    ] + [
        {
            "kind": "approval",
            "timestamp": approval["created_at"],
            "target_type": approval["target_type"],
            "status": approval["status"],
            "thread_id": approval["thread_id"],
        }
        for approval in approvals
    ]
    entries.sort(key=lambda e: e["timestamp"], reverse=True)
    return entries[:limit]
