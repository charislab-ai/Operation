-- 직원 명단: 각 AI 에이전트를 "직원"으로 등록해 CEO가 이름을 지어주고, 직급/직함/R&R과
-- 현재 업무 상태를 한 화면에서 볼 수 있게 한다.
--
-- Why 테이블인가: 이름은 CEO가 언제든 바꾸고(코드 배포 없이), 이름으로 부르면 그 직원만
-- 지시를 받는 라우팅에 쓰이며(app/graphs/supervisor.py), 입사 예정 직원을 CEO가 직접
-- 입사시키는(status 전환) 조작이 필요하기 때문.
create table if not exists employees (
  id uuid primary key default gen_random_uuid(),
  agent_key text unique not null,        -- 코드가 아는 식별자(그래프 노드와 1:1)
  name text not null,                    -- CEO가 지어준 이름. 지시문에서 이 이름을 부르면 본인 지목
  title text not null,                   -- 직함
  rank text not null,                    -- 직급
  department text not null,              -- 부서
  responsibilities text not null,        -- R&R
  run_agent_name text,                   -- agent_runs/ai_usage_log에 기록되는 이름(업무 상태 집계용)
  status text not null default 'active', -- active(재직) | onboarding(입사 예정) | leave(대기)
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table employees drop constraint if exists employees_status_check;
alter table employees add constraint employees_status_check
  check (status in ('active','onboarding','leave'));

insert into employees (agent_key, name, title, rank, department, responsibilities, run_agent_name, status, sort_order)
values
  ('supervisor', '비서실장', '비서실장', '실장', '경영',
   'CEO 지시를 읽고 어느 부서 일인지 판단해 배정하고, 부서별 킥오프 브리핑을 작성한다. 지시문에 특정 직원 이름이 있으면 그 직원에게 직접 전달한다.',
   'Supervisor', 'active', 10),
  ('performance_marketer', '퍼포먼스 마케터', '퍼포먼스 마케터', '팀장', '마케팅',
   '지난 게시물의 실제 성과와 게시 간격을 근거로 이번엔 어떤 제품을 어느 채널에 어떤 타깃·각도로 내보낼지 정한다. 감이 아니라 데이터로 결정하는 자리.',
   'PerformanceMarketer', 'onboarding', 20),
  ('marketing_director', '마케팅 디렉터', '마케팅 디렉터', '디렉터', '마케팅',
   '콘텐츠 형식(카드뉴스/인스타툰)과 장별 구성을 설계하고, 전문가들의 결과물을 하나의 게시물로 조립해 최종 검토한다.',
   'MarketingDirector', 'active', 30),
  ('copywriter', '카피라이터', '카피라이터', '선임', '마케팅',
   '카드 안에 들어가는 짧은 문구(헤드라인·보조문구)만 전담한다. 15자 안에서 시선을 잡는 훅을 쓰는 게 일.',
   'Copywriter', 'active', 40),
  ('social_editor', '소셜 에디터', '소셜 에디터', '선임', '마케팅',
   '피드에 노출되는 캡션·해시태그·CTA를 전담한다. 첫 줄 훅과 태그 조합으로 도달을 만드는 게 일.',
   'SocialEditor', 'active', 50),
  ('photo_art_director', '포토 아트디렉터', '포토 아트디렉터', '선임', '디자인',
   '각 장의 사진을 책임진다. 장면·조명·인물·구도를 정하고, 실제 앱 스크린샷을 쓸 자리를 고른다.',
   'PhotoArtDirector', 'active', 60),
  ('layout_designer', '레이아웃 디자이너', '레이아웃 디자이너', '선임', '디자인',
   '장마다 어떤 카드 틀로 조판할지 정한다. 틀 라이브러리에서 고르거나 여러 틀을 조합해 새 틀을 만든다.',
   'LayoutDesigner', 'active', 70),
  ('brand_qa', '브랜드 QA', '브랜드 QA', '책임', '품질',
   '완성된 카드 이미지를 직접 보고 글자 잘림·가독성·브랜드 톤 위반을 잡아낸다. 문제가 있으면 교정 지시를 내려 다시 그리게 한다.',
   'BrandQA', 'active', 80),
  ('publisher', '퍼블리셔', '퍼블리셔', '주임', '마케팅',
   'CEO 승인이 떨어진 게시물을 실제 채널에 올리고 게시 링크를 회수한다.',
   'Publisher', 'active', 90),
  ('dev_worker', '개발 담당', '개발 담당', '선임', '개발',
   '앱/서비스 코드 수정·버그 수정·기능 개발 제안서를 작성한다.',
   'DevWorker', 'active', 100)
on conflict (agent_key) do nothing;
