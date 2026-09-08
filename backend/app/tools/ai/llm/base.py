from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class Message(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    """ARCHITECTURE.md §7 — 추론 엔진 provider 어댑터 인터페이스. 특정 벤더에 고정하지 않는다.

    thread_id/agent_name은 업무 지시별 AI 사용량 로깅(app/db/ai_usage.py)을 위한
    선택적 컨텍스트 — 기본값 None이라 넘기지 않아도 동작한다.
    """

    async def complete(
        self,
        messages: list[Message],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> str: ...

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> SchemaT: ...
