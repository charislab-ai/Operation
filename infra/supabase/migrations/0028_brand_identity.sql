-- 계정 브랜드 정체성: 여러 앱(ChaMu·SNAPTAIL·터치러쉬)을 인스타 계정 하나로 홍보하는 구조라,
-- 앱별 브랜드북(products.tone_of_voice 등)만으로는 계정 톤이 앱마다 튄다. 팔로우할 이유가
-- "이 계정을 따라다닐 가치"에서 나오므로 계정 차원의 정체성을 따로 둔다.
create table if not exists brand_identity (
  id int primary key default 1,
  account_name text,          -- 계정이 스스로를 뭐라고 부르는가
  positioning text,           -- 한 줄 포지셔닝(무엇을 하는 계정인가)
  tone_of_voice text,         -- 말투
  audience text,              -- 누구에게 말하는가
  content_pillars text,       -- 다루는 주제 축(콘텐츠 기둥)
  cta_style text,             -- 행동 유도 방식
  core_hashtags text,         -- 매 게시물에 공통으로 쓰는 태그
  banned text,                -- 쓰지 않는 표현
  updated_at timestamptz not null default now(),
  constraint brand_identity_single_row check (id = 1)
);

insert into brand_identity (id, account_name, positioning, tone_of_voice, audience,
                            content_pillars, cta_style, core_hashtags, banned)
values (
  1,
  'CharisLab',
  '생활 속 작은 불편을 직접 만든 앱으로 푸는 1인 개발팀. 앱 자랑이 아니라 "이런 방법이 있다"를 알려주는 계정.',
  '과장 없이 담백하게, 아는 사람이 알려주듯. 반말 대신 편한 존댓말. 느낌표 남발 금지.',
  '아이폰·안드로이드를 쓰면서 "이거 왜 안 되지?" 하고 검색해본 적 있는 20~40대.',
  '① 폰 사용 중 겪는 불편과 해결법 ② 우리가 만든 앱이 그 문제를 푸는 방식 ③ 만드는 과정(1인 개발팀의 실제 이야기)',
  '팔로우보다 "저장"을 먼저 유도한다. 지금 필요 없어도 나중에 꺼내 쓸 이유를 준다.',
  '#차리스랩 #CharisLab #앱개발 #폰꿀팁',
  '최고, 1위, 혁신, 완벽 같은 과장 표현. 근거 없는 수치. "무료"를 제목에 반복해서 싸구려로 보이게 하는 것.'
)
on conflict (id) do nothing;
