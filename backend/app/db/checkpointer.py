from contextlib import AsyncExitStack

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import settings

_stack = AsyncExitStack()
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """FastAPI lifespan에서 1회 호출. interrupt()로 정지된 그래프 상태를 Postgres에 저장한다."""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    _checkpointer = await _stack.enter_async_context(
        AsyncPostgresSaver.from_conn_string(settings.supabase_db_url)
    )
    await _checkpointer.setup()
    return _checkpointer


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("checkpointer not initialized — call init_checkpointer() first")
    return _checkpointer


async def delete_thread_checkpoint(thread_id: str) -> None:
    """업무 지시 완전 삭제 시 LangGraph 체크포인트도 같이 지운다(안 지우면 같은 thread_id를
    나중에 재사용할 때 예전 상태가 남아있게 됨 - 이 프로젝트에서 thread_id는 UUID라 재사용될
    일은 없지만, 그래도 고아 데이터를 남기지 않기 위함)."""
    await get_checkpointer().adelete_thread(thread_id)


async def close_checkpointer() -> None:
    global _checkpointer
    await _stack.aclose()
    _checkpointer = None
