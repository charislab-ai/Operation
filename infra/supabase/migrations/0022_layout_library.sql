-- 벤치마킹으로 "찾은 카드 틀"을 기억하는 라이브러리.
-- 지금까지는 틀이 파이썬 코드에 하드코딩돼 있어서, 하루 2회 도는 벤치마킹이 스크랩북·밈·
-- 폴라로이드·체크리스트·인용구 등 14종 넘는 실제 인기 틀을 찾아내도 코드에 없으면 영원히 쓸 수
-- 없었다(결과물이 늘 같은 몇 개 틀로만 나온 원인). 이제 틀을 데이터로 저장하고, 비주얼 디자이너가
-- 요구사항에 맞는 틀을 골라 쓰거나 여러 개를 조합해 새 틀을 만든다. 새 틀은 코드 배포 없이 추가된다.
create table layout_library (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  when_to_use text not null,          -- 어떤 슬라이드에 어울리는지(디자이너 AI가 이걸 보고 고름)
  spec jsonb not null,                -- 조합형 레이아웃 스펙(layout_engine이 그대로 해석)
  source text,                        -- 어느 벤치마킹 회차에서 발견했는지
  enabled boolean not null default true,
  times_used int not null default 0,
  created_at timestamptz default now()
);
alter table layout_library enable row level security;
