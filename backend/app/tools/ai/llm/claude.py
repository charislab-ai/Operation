from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from app.config import settings
from app.tools.ai.llm.base import Message, SchemaT


@lru_cache
def _model() -> ChatAnthropic:
    # temperature를 명시하면 일부 최신 모델(예: claude-sonnet-5)이 "temperature is deprecated
    # for this model" 400 에러를 반환해 폴백 경로 자체가 죽는 걸 실측으로 확인 - 기본값 사용
    return ChatAnthropic(
        model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        max_tokens=4096,
    )


def _to_lc_messages(messages: list[Message]) -> list[tuple[str, str]]:
    return [(m.role, m.content) for m in messages]


class ClaudeLLMProvider:
    """LLMProvider 구현체 — Claude(Anthropic)를 기본 추론 엔진으로 사용한다."""

    async def complete(self, messages: list[Message]) -> str:
        result = await _model().ainvoke(_to_lc_messages(messages))
        return str(result.content)

    async def complete_structured(
        self, messages: list[Message], schema: type[SchemaT]
    ) -> SchemaT:
        structured_model = _model().with_structured_output(schema)
        result = await structured_model.ainvoke(_to_lc_messages(messages))
        return schema.model_validate(result)
