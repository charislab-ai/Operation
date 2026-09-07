-- CharisLab AI OS — Phase 2: Finance Agent 승인 상태 관리

alter table finance_entries add column status text check (status in ('draft','confirmed','rejected')) default 'draft';
alter table finance_entries add column created_at timestamptz default now();
alter table finance_entries add column merchant text;
alter table finance_entries add column raw_ocr jsonb;  -- Gemini Vision 원본 응답 보관 (디버깅/재처리용)
