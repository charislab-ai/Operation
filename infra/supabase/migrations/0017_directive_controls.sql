-- 승인 처리 중임을 원자적으로 표시하기 위한 상태값 추가('processing') + 강제종료 시 열린
-- 승인을 무효화하기 위한 상태값 추가('cancelled'). 실측으로 확인된 버그(반려해도 처리 중이던
-- 중복 실행이 새 승인을 계속 만들어냄)를 막기 위해 "지금 막 처리 시작함"을 DB에 즉시 기록한다.
alter table approvals drop constraint approvals_status_check;
alter table approvals add constraint approvals_status_check
  check (status in ('pending','processing','approved','rejected','revision','cancelled'));

-- 업무지시 단위 정지/강제종료 마킹
alter table directives add column paused_at timestamptz;
alter table directives add column terminated_at timestamptz;
