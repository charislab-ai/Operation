-- 업무 지시(work order)별 AI 사용량(토큰/이미지 수/실비용) 집계용 원자 로그.
-- LLM/이미지 생성 호출마다 한 행씩 best-effort로 남긴다(app/db/ai_usage.py::log_ai_usage -
-- 로깅 실패가 실제 그래프 실행을 막지 않음).
-- cost_usd는 provider가 실제 달러 금액을 주는 경우에만 채운다(Claude Code CLI의 total_cost_usd) -
-- API/이미지 경로는 토큰·장수만 기록하고 비용은 null로 남겨 허구의 숫자를 만들지 않는다.
create table ai_usage_log (
  id uuid primary key default gen_random_uuid(),
  thread_id text,
  agent_name text,
  provider text not null,              -- 'claude_cli'|'claude_api'|'dalle'|'mock'
  kind text not null check (kind in ('llm','image')),
  input_tokens int,
  output_tokens int,
  total_tokens int,
  image_count int,
  cost_usd numeric(10,4),
  created_at timestamptz default now()
);
create index ai_usage_log_thread_id_idx on ai_usage_log (thread_id);
create index ai_usage_log_agent_name_idx on ai_usage_log (agent_name);

alter table ai_usage_log enable row level security;
