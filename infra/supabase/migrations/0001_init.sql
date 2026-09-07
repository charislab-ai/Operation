-- CharisLab AI OS — 초기 스키마 (docs/ARCHITECTURE.md §3 참고)

create extension if not exists pgcrypto;
create extension if not exists vector;

-- 업무/일정
create table tasks (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  status text check (status in ('todo','in_progress','done')) default 'todo',
  dept text not null,                 -- 'CFO'|'CTO'|'CMO'|'CPO'|'CDO'|'CSO'
  assignee_agent text not null,
  start_date date,
  end_date date,
  wbs_parent_id uuid references tasks(id),
  progress_pct int default 0,
  created_at timestamptz default now()
);

create table schedules (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  task_id uuid references tasks(id),
  calendar_start timestamptz,
  calendar_end timestamptz
);

-- 마케팅
create table marketing_metrics (
  id uuid primary key default gen_random_uuid(),
  product text not null,              -- 'SPING'|'SnapTale'|...
  channel text not null,               -- 'instagram'|'facebook'|'tiktok'|'threads'
  metric_date date not null,
  impressions int default 0,
  clicks int default 0,
  conversions int default 0,
  post_id text
);

-- RAG 문서
create table documents (
  id uuid primary key default gen_random_uuid(),
  title text,
  source_path text,
  created_at timestamptz default now()
);

create table document_embeddings (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references documents(id),
  content text,
  embedding vector(1536)
);

-- 재무
create table finance_entries (
  id uuid primary key default gen_random_uuid(),
  entry_date date not null,
  debit_account text not null,
  credit_account text not null,
  amount numeric not null,
  category text,
  vat_flag boolean default false,
  receipt_url text
);

-- 승인/감사
create table approvals (
  id uuid primary key default gen_random_uuid(),
  target_type text not null,           -- 'marketing_post'|'finance_entry'|'pr_merge'
  target_id uuid,
  telegram_msg_id text,
  status text check (status in ('pending','approved','rejected','revision')) default 'pending',
  created_at timestamptz default now()
);

create table agent_runs (
  id uuid primary key default gen_random_uuid(),
  agent_name text not null,
  input jsonb,
  output jsonb,
  started_at timestamptz default now(),
  finished_at timestamptz
);

-- RLS: 모든 테이블은 백엔드(service_role, RLS 우회)를 통해서만 접근한다.
-- anon/authenticated용 정책을 두지 않아 프론트엔드의 직접 접근을 차단한다.
alter table tasks enable row level security;
alter table schedules enable row level security;
alter table marketing_metrics enable row level security;
alter table documents enable row level security;
alter table document_embeddings enable row level security;
alter table finance_entries enable row level security;
alter table approvals enable row level security;
alter table agent_runs enable row level security;
