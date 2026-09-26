-- 브랜드북: 제품별 톤·타깃·핵심 메시지·금지 표현을 "자산"으로 고정한다.
-- Why 에이전트가 아니라 컬럼인가: 브랜드 톤은 매번 새로 지어내는 게 아니라 지키는 것이라,
-- LLM에게 매번 생성시키면 회차마다 흔들린다. CEO가 앱관리 화면에서 한 번 정해두면
-- 카피라이터/소셜에디터/포토AD/레이아웃디자이너/브랜드QA가 전부 이 값을 참조한다.
alter table products add column if not exists tone_of_voice text;
alter table products add column if not exists target_audience text;
alter table products add column if not exists key_messages text;
alter table products add column if not exists banned_words text;
