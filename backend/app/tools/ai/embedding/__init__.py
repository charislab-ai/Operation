from functools import lru_cache

from app.config import settings
from app.tools.ai.embedding.base import EmbeddingProvider
from app.tools.ai.embedding.openai_embedding import OpenAIEmbeddingProvider


@lru_cache
def get_embedding() -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider()
    raise ValueError(f"unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")
