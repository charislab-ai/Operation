import logging
from functools import lru_cache

from app.config import settings
from app.tools.ai.image.base import ImageGenProvider
from app.tools.ai.image.dalle import DalleImageGenProvider
from app.tools.ai.image.gemini_image import GeminiImageGenProvider
from app.tools.ai.image.mock import MockImageGenProvider
from app.services.budget import assert_image_budget

logger = logging.getLogger(__name__)


class ImageGenFallbackChain:
    """1순위 provider가 실패(크레딧 소진, 서비스 장애 등)하면 2순위로 자동 전환.

    LLM 쪽 폴백(app/tools/ai/llm/__init__.py::LLMFallbackChain)과 같은 방침 - 원인을 세분화하지
    않고 실패하면 그냥 다음 벤더로 넘긴다. 이미지 생성은 그동안 폴백이 전혀 없어 벤더 장애 시
    카드뉴스/인스타툰이 통째로 멈추는 단일 장애 지점이었다(실측으로 겪음)."""

    def __init__(self, primary: ImageGenProvider, fallback: ImageGenProvider, label: str) -> None:
        self._primary = primary
        self._fallback = fallback
        self._label = label

    async def generate_bytes(self, prompt: str, *, thread_id=None, agent_name=None) -> bytes:
        assert_image_budget(thread_id)  # 상한 초과면 여기서 차단(폭주 방지)
        try:
            return await self._primary.generate_bytes(prompt, thread_id=thread_id, agent_name=agent_name)
        except Exception:
            logger.exception("%s 1순위 이미지 생성 실패 - 폴백으로 전환", self._label)
            return await self._fallback.generate_bytes(prompt, thread_id=thread_id, agent_name=agent_name)

    async def edit_bytes(self, reference_bytes: bytes, prompt: str, *, thread_id=None, agent_name=None) -> bytes:
        assert_image_budget(thread_id)  # 상한 초과면 여기서 차단(폭주 방지)
        try:
            return await self._primary.edit_bytes(
                reference_bytes, prompt, thread_id=thread_id, agent_name=agent_name
            )
        except Exception:
            logger.exception("%s 1순위 이미지 편집 실패 - 폴백으로 전환", self._label)
            return await self._fallback.edit_bytes(
                reference_bytes, prompt, thread_id=thread_id, agent_name=agent_name
            )


@lru_cache
def get_image_gen() -> ImageGenProvider:
    """카드뉴스 등 실사 사진 스타일 콘텐츠용 - OpenAI(gpt-image-1) 우선, Gemini 폴백.
    gpt-image-1이 실사 사진 스타일 생성에 강하다고 실측으로 확인됨(카드뉴스 프롬프트가 이 특성에
    맞춰 튜닝돼 있음)."""
    if settings.image_provider == "mock":
        return MockImageGenProvider()
    if settings.image_provider == "dalle":
        return ImageGenFallbackChain(DalleImageGenProvider(), GeminiImageGenProvider(), "card_news(OpenAI)")
    raise ValueError(f"unsupported IMAGE_PROVIDER: {settings.image_provider}")


@lru_cache
def get_instatoon_image_gen() -> ImageGenProvider:
    """인스타툰(마스코트 웹툰) 전용 - Gemini(gemini-3.1-flash-image) 우선, OpenAI 폴백.

    카드뉴스와 반대 순서인 이유: 같은 마스코트/장면으로 OpenAI(gpt-image-1)와 Gemini를 직접
    비교해본 결과(실측), Gemini 쪽이 "Korean webtoon style, simple line art, flat colors" 지시를
    훨씬 더 잘 따르고(OpenAI는 지시해도 그라데이션/글로시한 렌더링이 계속 섞여 나옴) 참조 이미지
    기반 캐릭터 일관성도 더 뛰어났다. 진짜 인스타툰처럼 보이는 게 이 형식의 핵심 가치이므로 여기선
    Gemini를 1순위로 둔다."""
    if settings.image_provider == "mock":
        return MockImageGenProvider()
    if settings.image_provider == "dalle":
        return ImageGenFallbackChain(GeminiImageGenProvider(), DalleImageGenProvider(), "instatoon(Gemini)")
    raise ValueError(f"unsupported IMAGE_PROVIDER: {settings.image_provider}")
