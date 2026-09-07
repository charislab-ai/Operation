from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings

EMBEDDING_MODEL = "text-embedding-3-small"  # documents.embedding vector(1536)과 차원 일치


@lru_cache
def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key)


class OpenAIEmbeddingProvider:
    """EmbeddingProvider 구현체 — RAG 문서/질의를 벡터로 변환한다."""

    async def embed(self, text: str) -> list[float]:
        response = await _client().embeddings.create(input=text, model=EMBEDDING_MODEL)
        return response.data[0].embedding
