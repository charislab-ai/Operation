from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class Message(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    """ARCHITECTURE.md §7 — 추론 엔진 provider 어댑터 인터페이스. 특정 벤더에 고정하지 않는다."""

    async def complete(self, messages: list[Message]) -> str: ...

    async def complete_structured(
        self, messages: list[Message], schema: type[SchemaT]
    ) -> SchemaT: ...
