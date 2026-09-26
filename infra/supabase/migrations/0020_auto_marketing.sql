-- 정기 자동 발행: CEO가 매번 지시하지 않아도 주기적으로 마케팅 콘텐츠를 만들어 결재에 올린다.
-- 설정은 단일 행으로 관리(id=1 고정) - 앱관리 화면에서 켜고 끄고 주기를 바꾼다.
create table marketing_auto_schedule (
  id int primary key default 1 check (id = 1),
  enabled boolean not null default false,
  interval_hours int not null default 72,     -- 며칠에 한 번 생성할지(시간 단위)
  products text[] not null default '{}',      -- 돌아가며 홍보할 앱 목록(비우면 products 테이블 전체)
  last_run_at timestamptz,
  last_product text,                          -- 마지막에 홍보한 앱(다음엔 그 다음 앱 차례)
  updated_at timestamptz default now()
);
insert into marketing_auto_schedule (id) values (1) on conflict do nothing;
alter table marketing_auto_schedule enable row level security;
