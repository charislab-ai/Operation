from functools import lru_cache

from app.config import settings
from app.tools.ai.image.base import ImageGenProvider
from app.tools.ai.image.dalle import DalleImageGenProvider
from app.tools.ai.image.mock import MockImageGenProvider


@lru_cache
def get_image_gen() -> ImageGenProvider:
    if settings.image_provider == "mock":
        return MockImageGenProvider()
    if settings.image_provider == "dalle":
        return DalleImageGenProvider()
    raise ValueError(f"unsupported IMAGE_PROVIDER: {settings.image_provider}")
