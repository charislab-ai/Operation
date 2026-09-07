from app.db.supabase_client import get_supabase
from app.tools.ai.embedding import get_embedding


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
