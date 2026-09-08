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
