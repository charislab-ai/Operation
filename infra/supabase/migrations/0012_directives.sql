-- CEO가 지금까지 제출한 모든 지시를 나열하기 위한 독립 테이블(업무 지시 카드 목록 화면).
-- approvals는 지시가 실제 워커까지 도달해 interrupt가 걸릴 때만 생기므로(즉시 완료되는 지시는
-- approvals가 없을 수 있음) 목록을 신뢰성있게 보여주려면 제출 시점에 원문을 별도로 남겨야 한다.
create table directives (
  id uuid primary key default gen_random_uuid(),
  thread_id text not null unique,
  ceo_directive text not null,
  created_at timestamptz default now()
);
create index directives_created_at_idx on directives (created_at desc);

alter table directives enable row level security;
-- 다른 테이블들과 동일하게 service_role 전용 - anon/authenticated용 정책 없음
