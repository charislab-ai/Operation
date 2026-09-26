from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class Message(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str
    # 이 메시지에 함께 붙일 이미지(PNG base64). 브랜드 QA가 완성된 카드를 "직접 보고" 검수할 때
    # 사용한다 - 텍스트만 오가던 구조에서는 렌더 결과(글자 잘림/대비 부족)를 아무도 확인할 수
    # 없었다. 이미지를 지원하지 않는 provider(Claude CLI)는 폴백으로 넘긴다.
    images: list[str] = []


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
