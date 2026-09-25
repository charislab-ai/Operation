-- 1) 텔레그램에서 "반려 사유"도 입력받을 수 있게 - 지금까지 awaiting_comment(boolean)은 보완만
--    가정했다. 어떤 결정을 기다리는 중인지(revision|rejected) 기록해야 답장을 제대로 처리한다.
alter table approvals add column awaiting_decision text
  check (awaiting_decision in ('revision','rejected'));

-- 2) 워커가 죽었을 때 CEO 화면에 "진행중"으로만 남던 문제 - 실패를 기록해서 보이게 한다.
--    (실측: OpenAI 크레딧 소진으로 RAG 임베딩이 429를 내면서 마케팅 파이프라인이 통째로 죽었는데
--     화면엔 아무 표시도 안 됐음)
alter table directives add column failed_at timestamptz;
alter table directives add column last_error text;
