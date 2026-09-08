import base64
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings
from app.db.ai_usage import log_ai_usage


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


class DalleImageGenProvider:
    """ImageGenProvider 구현체 — OpenAI 이미지 모델로 마케팅 카드의 배경 일러스트를 생성한다.

    실제로 겪은 이슈:
    - `dall-e-3`는 이 계정에서 이미 퇴역함(실측: "model does not exist") → `gpt-image-1`로 전환.
    - 이 모델은 `response_format="url"`을 거부하고 b64_json만 반환 → 여기선 그 바이트를 그대로
      돌려주고, 업로드/카드 합성은 호출부(card_composer)가 담당한다.
    - 정사각형(1024x1024)으로 생성해 카드의 가로로 넓은 사진 영역에 맞게 크롭하면 인물 머리
      윗부분이 잘려나가는 문제가 실측으로 확인됨 → 카드 사진 영역 비율에 가까운 와이드 사이즈로
      직접 생성해서 크롭량을 최소화한다.
    - `quality="high"`는 장당 비용이 커서(실측으로 테스트 중 몇 달러가 빠르게 소진됨) 기본을
      `medium`으로 낮춤 — 카드뉴스 용도로는 충분한 화질.
    """

    async def generate_bytes(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        response = await _client().images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1536x1024",
            quality=settings.image_quality,
            n=1,
        )
        usage = getattr(response, "usage", None)
        log_ai_usage(
            thread_id=thread_id,
            agent_name=agent_name,
            provider="dalle",
            kind="image",
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
            image_count=1,
            # gpt-image-1 응답엔 달러 비용이 없음 - 추정치를 지어내지 않고 토큰/장수만 기록
            cost_usd=None,
        )
        return base64.b64decode(response.data[0].b64_json)
