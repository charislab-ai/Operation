from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from app.auth.session import require_ceo
from app.db.supabase_client import get_supabase
from app.ws.manager import ConnectionManager

router = APIRouter(prefix="/agents", tags=["agents"])


def known_agents() -> list[str]:
    """추적할 에이전트 목록은 직원 명단(employees)에서 가져온다 - 조직이 바뀌면(직무 분할,
    신규 입사) 코드 수정 없이 따라오게 하기 위함. 실패 시 빈 목록(화면만 비어 보일 뿐 동작엔 지장 없음)."""
    try:
        rows = get_supabase().table("employees").select("run_agent_name").order("sort_order").execute().data
        return [r["run_agent_name"] for r in rows if r.get("run_agent_name")]
    except Exception:
        return []


ACTIVE_WINDOW = timedelta(minutes=5)

manager = ConnectionManager()


def _within_window(started_at_str: str) -> bool:
    started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) - started_at < ACTIVE_WINDOW


def compute_agent_status() -> list[dict]:
    supabase = get_supabase()
    result = []
    for agent_name in known_agents():
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
