-- agent_runs가 어느 LangGraph thread(CEO 지시 하나)에 속한 실행인지 추적한다.
-- approvals.thread_id(0002_phase1.sql)와 동일한 목적 - 업무 지시 상세 화면에서
-- 부서별 실행 타임라인을 조회하려면 필요.
alter table agent_runs add column thread_id text;
create index agent_runs_thread_id_idx on agent_runs (thread_id);
