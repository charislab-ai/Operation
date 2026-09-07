-- Supabase 보안 경고(rls_disabled_in_public) 대응: LangGraph AsyncPostgresSaver 체크포인터가
-- 자체적으로(init_checkpointer() -> checkpointer.setup()) 만드는 테이블들은 RLS를 모른 채
-- 생성되어 PostgREST로 공개 노출되고 있었다. 이 테이블들엔 CEO 지시/사업기획/마케팅 초안 등
-- 그래프 실행 상태가 그대로 담겨있어 그대로 두면 프로젝트 URL만으로 전체 조회/수정/삭제가 가능했다.
-- 백엔드는 이 테이블들을 service-role(REST) 또는 Postgres 직접연결(psycopg, RLS 우회)로만
-- 접근하므로, anon/authenticated 정책 없이 RLS만 켜면 앱 동작에는 영향 없이 공개 노출만 막힌다.
alter table checkpoints enable row level security;
alter table checkpoint_blobs enable row level security;
alter table checkpoint_writes enable row level security;
alter table checkpoint_migrations enable row level security;
