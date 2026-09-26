-- AI 사용량 상한(폭주 방지). 버그나 무한루프로 백그라운드에서 AI를 계속 호출해 크레딧이
-- 통째로 날아가는 걸 막기 위한 하드 리밋 - 상한에 걸리면 호출 자체를 차단하고 CEO에게 알린다.
create table ai_budget (
  id int primary key default 1 check (id = 1),
  enabled boolean not null default true,          -- false면 모든 AI 호출 차단(비상 정지 스위치)
  daily_image_limit int not null default 40,      -- 하루 이미지 생성 장수 상한
  daily_token_limit bigint not null default 3000000, -- 하루 LLM 토큰 상한
  per_thread_image_limit int not null default 15, -- 업무지시 1건당 이미지 장수 상한(루프 방어)
  updated_at timestamptz default now()
);
insert into ai_budget (id) values (1) on conflict do nothing;
alter table ai_budget enable row level security;
