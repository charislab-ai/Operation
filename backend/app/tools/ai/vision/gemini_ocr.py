import json
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings
from app.tools.ai.vision.base import ReceiptData

SYSTEM_PROMPT = """당신은 영수증 이미지를 분석하는 회계 보조 AI입니다. 이미지에서 가맹점명, 거래일자,
총 금액, 부가세 금액, 부가세 포함 여부, 지출 카테고리(식비/교통비/사무용품/광고비/기타 중 하나)를 추출하세요."""


@lru_cache
def _client() -> genai.Client:
    return genai.Client(api_key=settings.google_gemini_api_key)


class GeminiVisionOCRProvider:
    """VisionOCRProvider 구현체 — Gemini Vision으로 영수증을 분석한다 (ARCHITECTURE.md §7 기본값)."""

    async def extract_receipt(self, image: bytes, mime_type: str) -> ReceiptData:
        response = await _client().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=image, mime_type=mime_type),
                "이 영수증 이미지를 분석해주세요.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ReceiptData,
            ),
        )
        if response.parsed is not None:
            return response.parsed  # type: ignore[return-value]
        # SDK가 .parsed를 못 채운 경우를 대비한 방어적 폴백
        return ReceiptData.model_validate(json.loads(response.text))
