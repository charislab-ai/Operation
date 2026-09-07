# 외부 계정/설정 가이드 (Phase 0~1)

이 문서의 항목들은 각 외부 서비스의 본인 계정으로 직접 진행해야 하는 부분이라 Claude Code가 대신 처리할 수 없다. 완료할 때마다 [EXTERNAL_APIS.md](./EXTERNAL_APIS.md) 체크박스를 갱신한다.

## 1. Supabase

1. https://supabase.com 에서 새 프로젝트 생성
2. 프로젝트 설정 > API에서 `Project URL`, `service_role key`(백엔드용), `anon key`(프론트엔드용) 확인
3. SQL Editor에서 `infra/supabase/migrations/0001_init.sql` 내용 실행 (또는 Supabase CLI로 `supabase db push`) — 모든 테이블에 RLS를 켜고 정책은 두지 않아, 백엔드(service_role)만 접근 가능하고 프론트/anon 키로는 직접 접근이 차단된다.
4. `backend/.env`에 `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` 입력
5. `frontend/.env`에 `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` 입력

### 1.5 Postgres 직접 연결 (Phase 1, LangGraph checkpointer용)

`interrupt()`로 멈춘 그래프 상태를 저장하려면 Supabase REST(service-role)와는 별개로 **Postgres 직접 연결 문자열**이 필요하다.

1. Supabase 대시보드 → Project Settings → Database → Connection string
2. **Session pooler** 탭의 URI 복사 (비밀번호 포함, `postgresql://postgres.xxxx:[YOUR-PASSWORD]@...`)
3. `backend/.env`의 `SUPABASE_DB_URL`에 붙여넣기(비밀번호 부분을 실제 DB 비밀번호로 교체) — ⚠️ **`[YOUR-PASSWORD]`의 대괄호 `[` `]`는 표시일 뿐 실제 값에 포함하면 안 된다.** 대괄호를 그대로 남겨두면 `password authentication failed` 에러로 앱 시작이 실패한다(실제로 한 번 겪은 문제).
4. SQL Editor에서 `infra/supabase/migrations/0002_phase1.sql` 실행 (approvals 테이블에 `thread_id` 컬럼 추가)

> ⚠️ **`.env`와 `.env.example`을 혼동하지 말 것.** `.env.example`은 git에 커밋되는 템플릿이라 항상 빈 값이어야 하고, 실제 키는 반드시 `.env`(gitignore 처리됨)에만 넣는다. 특히 `SUPABASE_SERVICE_ROLE_KEY`는 RLS를 완전히 우회하는 최고권한 키라 노출되면 안 된다.

## 2. Google OAuth (로그인)

> **"내부(Internal)" 옵션이 안 보이는 이유:** Internal은 Google Workspace 조직 계정에서만 선택 가능하다. 개인 Gmail 계정으로 만든 프로젝트는 항상 External만 뜨는 게 정상이다. Workspace 없이도 아래 방법으로 동일하게 폐쇄형 접근을 만들 수 있다.

1. https://console.cloud.google.com 에서 프로젝트 생성
2. "API 및 서비스 > OAuth 동의 화면"에서:
   - User Type: **External** 선택 (선택지가 이것뿐이면 정상)
   - 게시 상태(Publishing status)를 **"Testing"으로 유지** (프로덕션으로 전환/게시하지 않음) — Testing 상태에서는 아래 "테스트 사용자"에 등록된 이메일만 로그인 가능해 사실상 폐쇄형이 되고, 우리가 쓰는 scope(email/profile, 로그인용 비민감 scope)는 Google의 앱 심사(verification) 없이도 기간 제한 없이 계속 쓸 수 있다.
   - "테스트 사용자(Test users)"에 CEO 본인 이메일(및 필요한 팀원 이메일) 등록 — 이 목록에 없는 계정은 로그인 화면에서 바로 차단된다.
3. "사용자 인증 정보 > OAuth 클라이언트 ID" 생성 (유형: 웹 애플리케이션)
   - 승인된 자바스크립트 원본: `http://localhost:5173`, `https://charislab.kr`
4. 발급된 Client ID를 `frontend/.env`의 `VITE_GOOGLE_OAUTH_CLIENT_ID`와 `backend/.env`의 `GOOGLE_OAUTH_CLIENT_ID`에 동일하게 입력
5. `backend/.env`의 `ALLOWED_EMAILS`에 로그인 허용할 이메일(쉼표 구분) 등록 — Google 콘솔의 "테스트 사용자"와 백엔드의 `ALLOWED_EMAILS` 두 군데 모두 등록해야 이중으로 막힌다(Google 단계 + 앱 자체 화이트리스트).

## 3. Telegram Bot (결재)

1. 텔레그램에서 `@BotFather`에게 `/newbot` 요청 → 봇 토큰 발급
2. 발급된 토큰을 `backend/.env`의 `TELEGRAM_BOT_TOKEN`에 입력
3. CEO 본인 계정의 chat_id 확인(예: `@userinfobot`과 대화) 후 `TELEGRAM_CEO_CHAT_ID`에 입력
4. 백엔드 배포 후 `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<백엔드주소>/telegram/webhook` 호출로 webhook 등록
   - **[보류 중]** localhost는 등록 불가(공인 HTTPS 주소 필요)라 정식 배포 시점까지 미룸. 배포 단계에서 다시 안내할 것.

## 4. Meta Graph API (Instagram/Facebook) — 심사 필요, 지금 신청 권장

1. https://developers.facebook.com 에서 앱 생성
2. 비즈니스 인증(Business Verification) 제출
3. `instagram_content_publish`, `instagram_basic`, `pages_manage_posts`, `pages_read_engagement` 권한 심사 신청
4. 승인 전까지는 `backend/.env`의 `SOCIAL_ADAPTER=mock` 유지 (승인 후 `meta`로 전환)

## 4.5. 이용약관/개인정보처리방침 URL

Meta/TikTok 앱 설정에는 Terms of Service URL, Privacy Policy URL이 필수다. `charislab.kr` 홈페이지 저장소(`/Volumes/Data/카리스랩/CL Homepage`)의 `/legal/ai-os` 페이지로 정식 등록해서 사용한다 (기존 `/legal` 페이지의 한/영 토글 디자인 재사용):

- Terms of Service: `https://charislab.kr/legal/ai-os?doc=terms`
- Privacy Policy: `https://charislab.kr/legal/ai-os?doc=privacy`

## 5. TikTok API — 심사 필요, 지금 신청 권장

1. https://developers.tiktok.com 에서 개발자 계정 등록
2. Content Posting API 접근 신청
3. 승인 전까지 Mock 어댑터로 개발 진행 (Phase 3까지 Mock 유지 가능)

## 6. AI 모델 API (Claude/OpenAI/Gemini)

특정 벤더에 고정하지 않는다 (ARCHITECTURE.md §7).

1. **Anthropic (Claude)**: 1순위는 **Claude Code CLI**(구독 플랜)를 그대로 사용 — 이 컴퓨터는 이미 로그인되어 있어 별도 설정 없이 Phase 1이 바로 동작한다(실측 확인됨). `ANTHROPIC_API_KEY`는 CLI가 한도 초과/실패할 때만 쓰이는 폴백이라 당장 필수는 아니지만, https://console.anthropic.com 에서 발급해 `backend/.env`에 넣어두면 안전하다.
   - ⚠️ **배포 시 주의**: `charislab.kr`에 실제 배포할 서버에는 로그인된 CLI가 없다. 그 서버에서도 CLI를 1순위로 쓰려면 `claude setup-token`으로 헤드리스 인증을 해둬야 한다. 안 해두면 배포 서버에서는 자동으로 API 키 폴백만 동작(그래서 API 키는 미리 받아두는 게 좋음).
2. **OpenAI**: https://platform.openai.com 에서 API 키 발급 → `OPENAI_API_KEY` (이미지/영상 생성용, Phase 3부터 필요)
3. **Google Gemini**: https://aistudio.google.com 에서 API 키 발급 → `GOOGLE_GEMINI_API_KEY` (Finance Agent 영수증 OCR용, Phase 2부터 필요)
4. 사용량/비용 한도 설정 권장

## 7. MCP 커넥터 (Canva/Figma/Google Calendar/Google Drive/Notion/Gmail)

이 항목들은 Claude Code/claude.ai 커넥터 설정에서 사용자가 직접 인증해야 하며, 코드 배포와는 별개다. `claude.ai` 계정 설정 > Connectors에서 각 서비스를 연결하면, 이후 Claude Code 세션에서 해당 MCP 툴을 바로 호출할 수 있다.

---

완료 후 로컬 실행: `backend/README.md`, `frontend/README.md` 참고. 두 서버를 각각 띄우면 `http://localhost:5173`에서 Google 로그인 후, 상단 지시 입력바에 CEO 지시를 입력해 실제로 WBS가 생성되고 Calendar View에 반영되는 흐름(Phase 1)을 테스트할 수 있다 — `ANTHROPIC_API_KEY`, `SUPABASE_DB_URL`, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CEO_CHAT_ID`가 모두 채워져 있어야 한다.
