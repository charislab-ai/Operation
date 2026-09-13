from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.auth.session import require_ceo
from app.db.supabase_client import get_supabase
from app.ws.manager import ConnectionManager

router = APIRouter(prefix="/agents", tags=["agents"])

KNOWN_AGENTS = [
    "Supervisor",
    "BizDevWorker",
    "PMWorker",
    "MarketingDirector",
    "ContentStrategist",
    "VisualDesigner",
    "DevWorker",
    "PublishWorker",
]
ACTIVE_WINDOW = timedelta(minutes=5)

manager = ConnectionManager()


def _within_window(started_at_str: str) -> bool:
    started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - started_at < ACTIVE_WINDOW


def compute_agent_status() -> list[dict]:
    supabase = get_supabase()
    result = []
    for agent_name in KNOWN_AGENTS:
        runs = (
            supabase.table("agent_runs")
            .select("*")
            .eq("agent_name", agent_name)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if not runs.data:
            result.append({"agent_name": agent_name, "status": "idle", "last_run": None})
            continue
        run = runs.data[0]
        is_active = run.get("finished_at") is None and _within_window(run["started_at"])
        result.append(
            {
                "agent_name": agent_name,
                "status": "active" if is_active else "idle",
                "last_run": run,
            }
        )
    return result


@router.get("/status")
def agent_status(_: str = Depends(require_ceo)) -> list[dict]:
    return compute_agent_status()


@router.websocket("/ws")
async def agent_status_ws(websocket: WebSocket, token: str | None = None) -> None:
    try:
        require_ceo(authorization=None, token=token)
    except HTTPException:
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        await websocket.send_json(compute_agent_status())
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
