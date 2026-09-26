-- 게시 성과 지표를 난수로 지어내던 걸 없애고(publish_worker), 대신 "실제로 어디에 올라갔는지"를
-- 남긴다. impressions/clicks/conversions는 실제 Insights API를 붙이기 전까지 null로 두고,
-- 지어낸 숫자로 판단하는 일이 없게 한다.
alter table marketing_metrics add column permalink text;
alter table marketing_metrics alter column impressions drop not null;
alter table marketing_metrics alter column clicks drop not null;
alter table marketing_metrics alter column conversions drop not null;
-- 이미 저장된 가짜 숫자 제거(실제 게시 기록 자체는 남김)
update marketing_metrics set impressions = null, clicks = null, conversions = null;
