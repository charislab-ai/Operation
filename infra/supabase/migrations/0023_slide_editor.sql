-- 승인 전 슬라이드 편집기: CEO가 결재 화면에서 문구/틀을 직접 고친 경우를 표시한다.
-- 편집된 내용은 approvals.payload(= marketing_post와 같은 모양)에 그대로 덮어써서 보관하고,
-- 그래프를 재개할 때 이 payload를 marketing_post로 되돌려 넣어 게시에 반영한다.
alter table approvals add column if not exists edited_at timestamptz;
