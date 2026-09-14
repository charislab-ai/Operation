-- 인스타툰(말풍선 만화) 형식 도입 - 앱별 고정 마스코트 캐릭터를 재사용하기 위한 컬럼.
-- mascot_asset_path: product-assets 버킷(이미 공개) 내 참조 이미지 경로, 시스템이 생성/갱신.
-- mascot_prompt: CEO가 캐릭터 묘사를 직접 커스터마이즈할 수 있는 필드(선택, 없으면 기본 템플릿 사용).
alter table products add column mascot_asset_path text;
alter table products add column mascot_prompt text;
