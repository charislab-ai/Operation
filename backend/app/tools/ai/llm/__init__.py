from functools import lru_cache

from app.config import settings
from app.tools.ai.llm.base import LLMProvider, Message, SchemaT
from app.tools.ai.llm.claude import ClaudeLLMProvider
from app.tools.ai.llm.claude_cli import ClaudeCLIProvider, ClaudeCLIUnavailable


class ClaudeCLIWithAPIFallback:
    """1순위 Claude Code CLI(구독 플랜 사용량 소진), 실패·한도초과 시 2순위 Anthropic API로 자동 전환.

    Why: CLI 요금제 사용량을 먼저 쓰고 초과분만 API 종량제로 넘겨 비용을 절감한다.
    (feedback_jarvis_no_api_switch와 동일한 원칙 — CLI를 기본으로 유지하고, 여기서는
    한도초과 시에만 API로 넘어가도록 명시적으로 설계된 폴백이지 임의 전환이 아니다.)
    """

    def __init__(self) -> None:
        self._cli = ClaudeCLIProvider()
        self._api = ClaudeLLMProvider()

    async def complete(self, messages: list[Message]) -> str:
        try:
            return await self._cli.complete(messages)
        except ClaudeCLIUnavailable:
            return await self._api.complete(messages)

    async def complete_structured(self, messages: list[Message], schema: type[SchemaT]) -> SchemaT:
        try:
            return await self._cli.complete_structured(messages, schema)
        except ClaudeCLIUnavailable:
            return await self._api.complete_structured(messages, schema)


@lru_cache
def get_llm() -> LLMProvider:
    if settings.llm_provider == "claude":
        return ClaudeCLIWithAPIFallback()
    raise ValueError(f"unsupported LLM_PROVIDER: {settings.llm_provider}")
