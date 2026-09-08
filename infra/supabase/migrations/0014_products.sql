-- 앱(제품) 정보를 코드에 하드코딩하지 않고 DB에서 관리한다 - "앱관리" 화면에서 CEO가 직접
-- 스토어 링크/브랜드 컬러/제품 설명을 수정할 수 있게 함. MarketingWorker가 지금까지
-- PRODUCT_STORE_LINKS/PRODUCT_BRAND_COLORS로 하드코딩해 쓰던 값(브랜드 컬러는 미확인 추정치였음)을
-- 여기로 옮긴다.
create table products (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,   -- MarketingWorker의 product 키와 정확히 일치해야 함 ('ChaMu'|'SNAPTAIL'|'터치러쉬')
  ios_url text,
  android_url text,
  brand_color text,            -- '#RRGGBB'
  description text,            -- 앱 특징/설명 (마케팅 카피 참고용)
  updated_at timestamptz default now()
);

alter table products enable row level security;

-- 실제 출시된 3개 앱으로 시드 (docs/PRD.md, backend/app/graphs/workers/marketing_worker.py 기준).
-- 브랜드 컬러는 기존 코드의 추정치를 그대로 옮긴 것 - CEO가 앱관리 화면에서 정확한 값으로 수정 가능.
insert into products (name, ios_url, android_url, brand_color, description) values
  ('ChaMu', 'https://apps.apple.com/app/id6801702365', null, '#6366F1',
   '벨소리 만들기, 동영상에서 음원 추출, 친구/가족이 보내준 mp3 다운받아 바로 재생 (iOS 전용)'),
  ('SNAPTAIL', 'https://apps.apple.com/app/id6760613767', 'https://play.google.com/store/apps/details?id=com.charisro.snaptail', '#2563EB',
   '사진 보관, 사진에 설명 추가, PDF로 저장/출력, 가족·직장·여행·취미 등 사진첩별 관리'),
  ('터치러쉬', 'https://apps.apple.com/app/id6751933591', 'https://play.google.com/store/apps/details?id=com.charisro.TouchRush', '#A855F7',
   '동물을 빠르게 터치하는 반응속도 게임. 포유류만 터치, 파충류/조류를 터치하면 생명 감소 - 순발력과 상황판단력 필요');
