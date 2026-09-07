from functools import lru_cache

from app.config import settings
from app.tools.ai.vision.base import ReceiptData, VisionOCRProvider
from app.tools.ai.vision.gemini_ocr import GeminiVisionOCRProvider


@lru_cache
def get_vision_ocr() -> VisionOCRProvider:
    if settings.vision_provider == "gemini":
        return GeminiVisionOCRProvider()
    raise ValueError(f"unsupported VISION_PROVIDER: {settings.vision_provider}")
