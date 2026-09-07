-- CharisLab AI OS — Phase 4: Metaverse 사무실 책상 배치 (룸은 프론트 고정 템플릿, 책상만 영속화)

create table office_desks (
  id uuid primary key default gen_random_uuid(),
  room text not null,          -- '대표실'|'개발실'|'마케팅실'|'경영지원실'
  grid_x int not null,
  grid_y int not null,
  dept text,                   -- 'CFO'|'CTO'|'CMO'|'CPO'|'CDO'|'CSO'
  label text,                  -- 표시용 이름 (예: 'PM Agent')
  created_at timestamptz default now(),
  unique (room, grid_x, grid_y)
);

alter table office_desks enable row level security;
