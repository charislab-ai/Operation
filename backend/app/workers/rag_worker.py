import asyncio
import logging

from app.db.supabase_client import get_supabase
from app.tools.ai.embedding import get_embedding

logger = logging.getLogger(__name__)


def chunk_text(text: str, max_chars: int = 800) -> list[str]:
    """문단 단위로 자르되 max_chars를 넘지 않게 합친다 — RAG 첫 구현이라 단순한 규칙 기반 청킹으로 충분."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) + len(p) > max_chars:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks or [text]


async def rag_search(query: str, limit: int = 5) -> list[dict]:
    """API(app/api/documents.py)와 DevWorker(app/graphs/workers/dev_worker.py)가 공유하는 검색 함수."""
    vector = await get_embedding().embed(query)
    result = (
        get_supabase()
        .rpc("match_documents", {"query_embedding": vector, "match_count": limit})
        .execute()
    )
    return result.data


async def rag_search_safe(query: str, limit: int = 5, timeout: float = 20.0) -> list[dict]:
    """그래프 워커 전용 - RAG 검색이 실패해도 절대 작업 전체를 죽이지 않는다.

    Why: RAG는 "참고 문서가 있으면 더 좋은 결과"를 위한 부가 기능인데, 임베딩(OpenAI) 호출
    하나가 실패하면 마케팅 파이프라인 전체가 첫 단계에서 죽어버리는 게 실측으로 확인됐다
    (OpenAI 크레딧 소진 → 429 → MarketingDirector 노드 사망 → CEO 화면엔 "진행중"만 영원히).
    부가 기능 실패는 부가 기능 실패로만 끝나야 하므로 예외/타임아웃을 여기서 흡수하고 빈
    목록을 반환한다. API 엔드포인트(app/api/documents.py)는 에러가 그대로 보여야 하므로
    기존 rag_search를 그대로 쓴다.
    """
    try:
        return await asyncio.wait_for(rag_search(query, limit), timeout=timeout)
    except Exception:
        logger.exception("RAG 검색 실패 - 참고 문서 없이 계속 진행")
        return []
