-- 게시 성과 실측 수집: 지금까지는 "어디에 올렸는지"만 남기고 성과는 비워뒀다(지어낸 숫자를
-- 쓰지 않기 위해). instagram_manage_insights 권한이 붙어 실제 지표를 받을 수 있게 됐으므로
-- 조회·도달·저장·공유를 저장한다(app/services/insights.py).
alter table marketing_metrics add column if not exists views int;
alter table marketing_metrics add column if not exists reach int;
alter table marketing_metrics add column if not exists saved int;
alter table marketing_metrics add column if not exists shares int;
alter table marketing_metrics add column if not exists likes int;
alter table marketing_metrics add column if not exists comments int;
alter table marketing_metrics add column if not exists profile_visits int;
alter table marketing_metrics add column if not exists follows int;
alter table marketing_metrics add column if not exists media_type text;
alter table marketing_metrics add column if not exists collected_at timestamptz;

-- 계정 전체 추이(팔로워 증감 등) - 게시물 단위 지표로는 "계정이 자라는지"를 알 수 없다.
create table if not exists account_snapshots (
  id uuid primary key default gen_random_uuid(),
  channel text not null,
  snapshot_date date not null,
  followers int,
  media_count int,
  reach int,           -- 최근 1일 도달(계정 단위)
  profile_views int,
  created_at timestamptz not null default now(),
  unique (channel, snapshot_date)
);
