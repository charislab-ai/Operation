from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings
from app.db.ai_usage import log_ai_usage


@lru_cache
def _client() -> genai.Client:
    return genai.Client(api_key=settings.google_gemini_api_key)


def _extract_image_bytes(response) -> bytes:
    candidates = response.candidates or []
    for candidate in candidates:
        for part in (candidate.content.parts if candidate.content else []) or []:
            if part.inline_data and part.inline_data.data:
                return part.inline_data.data
    raise ValueError("Gemini 응답에 이미지 파트가 없음 - 프롬프트가 정책에 걸렸을 수 있음")


class GeminiImageGenProvider:
    """ImageGenProvider 구현체 — OpenAI(gpt-image-1)가 실패했을 때(크레딧 소진 등) 쓰는 폴백.

    Imagen 전용 편집 API는 Vertex 권한이 따로 필요해 이 프로젝트의 일반 Gemini Developer API
    키로는 못 쓸 수 있어서, generate_content가 지원하는 멀티모달 이미지 생성 모델
    (gemini-2.5-flash-image, 일명 "나노바나나")을 쓴다 - 텍스트 프롬프트만으로 생성도 되고,
    참조 이미지를 함께 넣으면 그 이미지를 기반으로 편집도 된다(마스코트 일관성 유지에 그대로 재사용
    가능). OCR(gemini_ocr.py)과 같은 GOOGLE_GEMINI_API_KEY를 재사용한다.
    """

    async def generate_bytes(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        response = await _client().aio.models.generate_content(
            model=settings.gemini_image_model,
            contents=prompt,
        )
        log_ai_usage(thread_id=thread_id, agent_name=agent_name, provider="gemini", kind="image", image_count=1)
        return _extract_image_bytes(response)

    async def edit_bytes(
        self,
        reference_bytes: bytes,
        prompt: str,
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> bytes:
        response = await _client().aio.models.generate_content(
            model=settings.gemini_image_model,
            contents=[types.Part.from_bytes(data=reference_bytes, mime_type="image/png"), prompt],
        )
        log_ai_usage(thread_id=thread_id, agent_name=agent_name, provider="gemini", kind="image", image_count=1)
        return _extract_image_bytes(response)
