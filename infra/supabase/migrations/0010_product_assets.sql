-- 실제 앱 스크린샷 등록용 - MarketingWorker가 AI 생성 대신 실제 화면을 카드뉴스 슬라이드에 쓸 수 있게 함
create table product_assets (
  id uuid primary key default gen_random_uuid(),
  product text not null,
  storage_path text not null,
  description text not null,  -- 이 화면이 뭘 보여주는지(예: "벨소리 만들기 편집 화면") - LLM이 이걸 보고 적절한 슬라이드에 매칭
  created_at timestamptz default now()
);

alter table product_assets enable row level security;
