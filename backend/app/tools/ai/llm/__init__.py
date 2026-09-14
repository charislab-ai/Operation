import logging
from functools import lru_cache

from app.config import settings
from app.tools.ai.llm.base import LLMProvider, Message, SchemaT
from app.tools.ai.llm.claude import ClaudeLLMProvider
from app.tools.ai.llm.claude_cli import ClaudeCLIProvider, ClaudeCLIUnavailable
from app.tools.ai.llm.gemini import GeminiLLMProvider

logger = logging.getLogger(__name__)


class LLMFallbackChain:
    """1순위 Claude Code CLI(구독 플랜), 2순위 Anthropic API(종량제), 3순위 Gemini.

    Why 1→2: CLI 요금제 사용량을 먼저 쓰고 초과분만 API 종량제로 넘겨 비용을 절감한다
    (feedback_jarvis_no_api_switch와 동일한 원칙 — CLI를 기본으로 유지하고, 여기서는
    한도초과 시에만 API로 넘어가도록 명시적으로 설계된 폴백이지 임의 전환이 아니다). 단,
    운영 서버(Railway) 컨테이너엔 claude CLI 자체가 없어 실제 운영에서는 사실상 곧장 2번으로
    간다 - CLI 폴백은 로컬 개발 환경에서만 실제로 의미가 있다.

    Why 2→3: Anthropic API 쪽 장애(크레딧 소진, 서비스 장애 등)로 2번까지 실패하면 완전히
    다른 벤더인 Gemini로 넘어가 서비스가 통째로 멈추는 걸 막는다(실측으로 겪음 - Anthropic
    크레딧 소진 시 모든 부서 작업이 막혔었음). CLI→API 폴백과 같은 방침으로, 원인을 세분화하지
    않고 실패하면 그냥 다음 단계로 넘긴다(과도하게 방어적으로 에러를 구분하려 하지 않음 -
    claude_cli.py의 기존 설계 원칙과 동일).
    """

    def __init__(self) -> None:
        self._cli = ClaudeCLIProvider()
        self._api = ClaudeLLMProvider()
        self._gemini = GeminiLLMProvider()

    async def complete(
        self,
        messages: list[Message],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        try:
            return await self._cli.complete(messages, thread_id=thread_id, agent_name=agent_name)
        except ClaudeCLIUnavailable:
            pass
        try:
            return await self._api.complete(messages, thread_id=thread_id, agent_name=agent_name)
        except Exception:
            logger.exception("Anthropic API 실패 - Gemini로 폴백")
            return await self._gemini.complete(messages, thread_id=thread_id, agent_name=agent_name)

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> SchemaT:
        try:
            return await self._cli.complete_structured(
                messages, schema, thread_id=thread_id, agent_name=agent_name
            )
        except ClaudeCLIUnavailable:
            pass
        try:
            return await self._api.complete_structured(
                messages, schema, thread_id=thread_id, agent_name=agent_name
            )
        except Exception:
            logger.exception("Anthropic API 실패 - Gemini로 폴백")
            return await self._gemini.complete_structured(
                messages, schema, thread_id=thread_id, agent_name=agent_name
            )


@lru_cache
def get_llm() -> LLMProvider:
    if settings.llm_provider == "claude":
        return LLMFallbackChain()
    raise ValueError(f"unsupported LLM_PROVIDER: {settings.llm_provider}")
