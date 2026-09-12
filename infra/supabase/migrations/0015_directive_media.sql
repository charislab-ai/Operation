-- CEO가 지시에 첨부한 이미지/동영상 - 텍스트로만 참조되며(파일명/URL/캡션) 이 단계에서는
-- 어떤 워커도 비전 모델로 내용을 분석하지 않는다(범위 밖, 추후 별도 기능).
-- 웹 작성 모달(POST /directives, POST /directives/{thread_id}/media)과 텔레그램 "/지시" 명령
-- 둘 다 이 테이블에 쓴다 - 저장 경로는 같지만 진입점만 다름.
create table directive_media (
  id uuid primary key default gen_random_uuid(),
  thread_id text not null references directives (thread_id) on delete cascade,
  storage_path text not null,
  media_type text not null check (media_type in ('image', 'video')),
  caption text,
  created_at timestamptz default now()
);
create index directive_media_thread_id_idx on directive_media (thread_id);

alter table directive_media enable row level security;
-- 다른 테이블들과 동일하게 service_role 전용 - anon/authenticated용 정책 없음
