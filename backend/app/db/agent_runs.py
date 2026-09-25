import asyncio
from datetime import datetime, timezone

from app.db.supabase_client import get_supabase


def _notify_status_change() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    from app.api.agents import compute_agent_status, manager

    loop.create_task(manager.broadcast(compute_agent_status()))


def start_run(agent_name: str, input_data: dict, thread_id: str | None = None) -> str:
    row = {"agent_name": agent_name, "input": input_data}
    if thread_id:
        row["thread_id"] = thread_id
    result = get_supabase().table("agent_runs").insert(row).execute()
    _notify_status_change()
    return result.data[0]["id"]


def finish_run(run_id: str, output_data: dict) -> None:
    get_supabase().table("agent_runs").update(
        {"output": output_data, "finished_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", run_id).execute()
    _notify_status_change()


def fail_unfinished_runs(thread_id: str, error_message: str) -> int:
    """이 지시(thread)에서 아직 안 끝난 워커 실행들을 "실패"로 마감한다.

    Why: 워커가 예외로 죽으면 finish_run이 호출되지 않아 agent_runs에 started_at만 있고
    finished_at이 영원히 비어있는 유령 행이 남았고(실측: 마케팅 파이프라인이 OpenAI 크레딧
    소진으로 죽었을 때 그대로 재현됨), 화면엔 "진행중"으로만 보여 CEO가 원인을 알 수 없었다.
    """
    supabase = get_supabase()
    rows = (
        supabase.table("agent_runs")
        .select("id")
        .eq("thread_id", thread_id)
        .is_("finished_at", "null")
        .execute()
        .data
    )
    for row in rows:
        supabase.table("agent_runs").update(
            {"output": {"error": error_message}, "finished_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", row["id"]).execute()
    if rows:
        _notify_status_change()
    return len(rows)
