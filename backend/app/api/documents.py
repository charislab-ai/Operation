from fastapi import APIRouter
from pydantic import BaseModel

from app.db.supabase_client import get_supabase
from app.tools.ai.embedding import get_embedding
from app.workers.rag_worker import chunk_text, rag_search

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    title: str
    content: str
    source_path: str | None = None


class DocumentOut(BaseModel):
    id: str
    title: str | None = None
    source_path: str | None = None


class SearchResult(BaseModel):
    document_id: str
    content: str
    similarity: float


@router.post("", response_model=DocumentOut)
async def create_document(payload: DocumentCreate) -> dict:
    supabase = get_supabase()
    doc = (
        supabase.table("documents")
        .insert({"title": payload.title, "source_path": payload.source_path})
        .execute()
    )
    document_id = doc.data[0]["id"]

    embedder = get_embedding()
    for chunk in chunk_text(payload.content):
        vector = await embedder.embed(chunk)
        supabase.table("document_embeddings").insert(
            {"document_id": document_id, "content": chunk, "embedding": vector}
        ).execute()

    return {"id": document_id, "title": payload.title, "source_path": payload.source_path}


@router.get("/search", response_model=list[SearchResult])
async def search_documents(q: str, limit: int = 5) -> list[dict]:
    return await rag_search(q, limit)
