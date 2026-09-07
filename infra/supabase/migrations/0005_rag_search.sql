-- CharisLab AI OS — Phase 4: RAG 벡터 검색 RPC
-- Supabase REST(postgrest)는 벡터 유사도 검색을 직접 지원하지 않아 Postgres 함수로 노출한다.

create or replace function match_documents(
  query_embedding vector(1536),
  match_count int default 5
)
returns table (
  id uuid,
  document_id uuid,
  content text,
  similarity float
)
language sql stable
as $$
  select
    document_embeddings.id,
    document_embeddings.document_id,
    document_embeddings.content,
    1 - (document_embeddings.embedding <=> query_embedding) as similarity
  from document_embeddings
  order by document_embeddings.embedding <=> query_embedding
  limit match_count;
$$;
