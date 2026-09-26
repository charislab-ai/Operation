-- 입사 추천 알림: 입사 예정(onboarding) 직원의 입사 조건이 채워지면 CEO에게 한 번 알리고,
-- 같은 추천을 반복해서 보내지 않도록 보낸 시각을 남긴다.
-- (CEO가 "얼마나 쌓여야 하는지 나는 모른다"고 해서, 조건 충족 여부를 시스템이 감시하고 먼저 알린다)
alter table employees add column if not exists hire_recommended_at timestamptz;
