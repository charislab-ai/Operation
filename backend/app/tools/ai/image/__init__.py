import logging
from functools import lru_cache

from app.config import settings
from app.tools.ai.image.base import ImageGenProvider
from app.tools.ai.image.dalle import DalleImageGenProvider
from app.tools.ai.image.gemini_image import GeminiImageGenProvider
from app.tools.ai.image.mock import MockImageGenProvider

logger = logging.getLogger(__name__)


class ImageGenFallbackChain:
    """1순위 OpenAI(gpt-image-1), 실패 시(크레딧 소진, 서비스 장애 등) 2순위 Gemini로 자동 전환.

    LLM 쪽 폴백(app/tools/ai/llm/__init__.py::LLMFallbackChain)과 같은 방침 - 원인을 세분화하지
    않고 실패하면 그냥 다음 벤더로 넘긴다. 이미지 생성은 그동안 폴백이 전혀 없어 OpenAI 장애 시
    카드뉴스/인스타툰이 통째로 멈추는 단일 장애 지점이었다(실측으로 겪음)."""

    def __init__(self) -> None:
        self._primary = DalleImageGenProvider()
        self._fallback = GeminiImageGenProvider()

    async def generate_bytes(self, prompt: str, *, thread_id=None, agent_name=None) -> bytes:
        try:
            return await self._primary.generate_bytes(prompt, thread_id=thread_id, agent_name=agent_name)
        except Exception:
            logger.exception("OpenAI 이미지 생성 실패 - Gemini로 폴백")
            return await self._fallback.generate_bytes(prompt, thread_id=thread_id, agent_name=agent_name)

    async def edit_bytes(self, reference_bytes: bytes, prompt: str, *, thread_id=None, agent_name=None) -> bytes:
        try:
            return await self._primary.edit_bytes(
                reference_bytes, prompt, thread_id=thread_id, agent_name=agent_name
            )
        except Exception:
            logger.exception("OpenAI 이미지 편집 실패 - Gemini로 폴백")
            return await self._fallback.edit_bytes(
                reference_bytes, prompt, thread_id=thread_id, agent_name=agent_name
            )


@lru_cache
def get_image_gen() -> ImageGenProvider:
    if settings.image_provider == "mock":
        return MockImageGenProvider()
    if settings.image_provider == "dalle":
        return ImageGenFallbackChain()
    raise ValueError(f"unsupported IMAGE_PROVIDER: {settings.image_provider}")
