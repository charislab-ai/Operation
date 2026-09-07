-- CharisLab AI OS — Phase 1: LangGraph 오케스트레이션 (docs/PHASE_PLAN.md Phase 1 참고)

-- approvals가 LangGraph의 어느 실행(thread)에 대한 승인 요청인지 추적
alter table approvals add column thread_id text;
create index approvals_thread_id_idx on approvals (thread_id);
