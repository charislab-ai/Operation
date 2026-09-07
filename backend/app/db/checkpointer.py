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


async def close_checkpointer() -> None:
    global _checkpointer
    await _stack.aclose()
    _checkpointer = None
