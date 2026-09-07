import base64
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


class DalleImageGenProvider:
    """ImageGenProvider 구현체 — OpenAI 이미지 모델로 마케팅 카드의 배경 일러스트를 생성한다.

    실제로 겪은 이슈:
    - `dall-e-3`는 이 계정에서 이미 퇴역함(실측: "model does not exist") → `gpt-image-1`로 전환.
    - 이 모델은 `response_format="url"`을 거부하고 b64_json만 반환 → 여기선 그 바이트를 그대로
      돌려주고, 업로드/카드 합성은 호출부(card_composer)가 담당한다.
    """

    async def generate_bytes(self, prompt: str) -> bytes:
        response = await _client().images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            quality="high",
            n=1,
        )
        return base64.b64decode(response.data[0].b64_json)
