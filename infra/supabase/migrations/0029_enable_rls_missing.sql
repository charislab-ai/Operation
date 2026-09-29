-- 보안: 최근 추가한 세 테이블에 RLS를 켜지 않아 공개 노출 상태였다(Supabase 보안 경고로 확인).
-- 이 프로젝트 방침은 0001_init.sql과 동일하다 - 모든 테이블은 백엔드(service_role, RLS 우회)를
-- 통해서만 접근하고, anon/authenticated용 정책을 두지 않아 외부 직접 접근을 차단한다.
alter table employees enable row level security;
alter table brand_identity enable row level security;
alter table account_snapshots enable row level security;
