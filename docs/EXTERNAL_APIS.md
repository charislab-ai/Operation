# CharisLab AI OS — 외부 연동 체크리스트

이 문서는 Phase 진행 중 계속 업데이트하는 **살아있는 문서**다. 신청/승인 상태가 바뀔 때마다 갱신한다.

## Meta Graph API (Instagram / Facebook)

- [x] Meta for Developers 앱 등록
- [x] 비즈니스 인증(Business Verification) 제출
- [ ] 필요 권한 확보 — Graph API Explorer에서 아래 권한 체크 후 토큰 발급
  - `instagram_basic`
  - `instagram_content_publish`
  - `pages_show_list` / `pages_read_engagement`
  - **주의(2026-08-26 정정)**: `instagram_business_basic`/`instagram_business_content_publish`는 "Instagram 계정으로 직접 로그인"하는 **별도의 새 플로우**(Instagram Login) 전용 권한명이고, 우리는 **페이스북 페이지에 연결된 인스타그램 비즈니스 계정** 방식(Facebook Login 기반 Instagram Graph API)을 쓰므로 위의 예전 이름(`instagram_basic` 등)이 맞다 — 실제로 Graph API Explorer 권한 목록에 새 이름이 아예 안 뜨는 것으로 실측 확인함(이전에 "개편으로 명칭 변경"이라고 적었던 건 착오).
- [x] 통합 계정 생성: Facebook 페이지 "CharisLab"(Page ID `1309299538928884`) + Instagram 비즈니스 계정 `@charislab.hq`(ID `17841433523128483`), 서로 연결 완료
- [x] Graph API Explorer에서 `pages_show_list`/`pages_read_engagement`/`instagram_basic`/`instagram_content_publish` 권한으로 토큰 발급 → `fb_exchange_token`으로 장기 사용자 토큰(60일) 교환 → 그걸로 Page Access Token 재발급하면 **`expires_at: 0`(비만료)** 확인됨. `backend/.env`에 `META_APP_ID`/`META_APP_SECRET`/`META_PAGE_ACCESS_TOKEN`/`META_PAGE_ID`/`META_INSTAGRAM_BUSINESS_ACCOUNT_ID` 전부 반영 완료(2026-09-07 실제 발급 확인)
- [ ] `app/tools/social/meta.py` 실제 게시 로직 구현 (아직 스텁) — 다음 작업
- [ ] `IMAGE_PROVIDER=dalle`, `SOCIAL_ADAPTER=meta`로 전환 후 실제 게시 1건 테스트
- 상태: **계정/토큰 준비 완료, 실연동 코드 구현 대기**
- 참고: 본인 소유 계정(자사 제품)만 대상이면 **Standard Access**로 심사 없이 즉시 사용 가능 — 실제로 심사 없이 위 권한이 바로 발급됨(Advanced Access 불필요했음).

## Threads API

- [ ] Threads 관련 권한 확보 (Meta 앱 안에 이미 "Threads API 액세스" 유스케이스 존재 — 별도 앱 등록 불필요, 같은 앱에서 권한만 추가)
  - `threads_business_basic`
  - `threads_business_content_publish` (권한 목록에서 "publish"로 검색해 정확한 명칭 확인)
- 상태: **진행중**
- 참고: Instagram과 마찬가지로 본인 계정 한정이면 Standard Access로 심사 없이 진행 가능.

## TikTok API

- [x] TikTok for Developers 앱 등록 (CharisLAB AI OS)
- [x] Login Kit 추가 (Content Posting API 선행조건)
- [x] Content Posting API 추가 (Production 탭)
- [x] 통합 계정("CharisLab") 생성 + Sandbox Target User 등록 완료
- [x] App details 저장 완료 (Description, Platforms: Web, Redirect URI: `https://charislab.kr/operation/auth/tiktok/callback` — 백엔드에 이 콜백 엔드포인트는 Phase 3에서 실제 구현 필요)
- [ ] Sandbox에서 실제 영상 업로드 API 호출 테스트 (Phase 3에서 `tools/social/tiktok.py` 구현 시 진행)
- [ ] Client key/secret을 `backend/.env`의 `TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET`에 입력
- 상태: **Sandbox 테스트 준비 완료** (Production 심사는 Phase 5로 보류)
- 참고: Production 심사(App Review, 데모 영상 등)는 Phase 5(실연동 확장) 때 진행. 지금은 Sandbox + Target User만으로 충분.

## Google Analytics (GA4)

- [ ] GA4 속성 생성 (또는 기존 제품 GA4 속성 확인)
- [ ] 연동 방식 결정: Measurement Protocol(서버 이벤트 전송) vs Data API(리포트 조회)
- 상태: **미착수**

## Telegram Bot (Human-in-the-Loop 결재)

- [x] BotFather로 봇 생성 및 토큰 발급 (`backend/.env`의 `TELEGRAM_BOT_TOKEN`에 반영됨)
- [x] CEO 텔레그램 chat_id 확보 및 `TELEGRAM_CEO_CHAT_ID`에 입력
- [x] Phase 1: 승인 요청 전송(`send_approval_request`) + webhook에서 승인/반려/보완 파싱 및 그래프 resume 로직 구현 완료
- [ ] Webhook URL 등록 (백엔드 `/telegram/webhook`) — **정식 배포 후 진행** (localhost로는 등록 불가, 배포 시점에 다시 안내). 등록 시 `setWebhook` 호출에 `secret_token=<backend .env의 TELEGRAM_WEBHOOK_SECRET>`을 반드시 같이 넘길 것 — 텔레그램이 이후 모든 webhook 요청에 `X-Telegram-Bot-Api-Secret-Token` 헤더로 이 값을 실어보내고, 백엔드가 이를 검증해 위조 요청을 막는다(Phase 5, ARCHITECTURE.md §8)
- 상태: **진행중** (토큰/chat_id 완료, 코드 구현 완료, webhook 등록만 배포 대기)

## Google OAuth (로그인)

- [x] Google Cloud Console 프로젝트 생성
- [x] OAuth 동의 화면 설정 (External + Testing 모드, 테스트 사용자 등록)
- [x] 클라이언트 ID/Secret 발급 (`backend/.env`, `frontend/.env`에 반영됨), `ALLOWED_EMAILS` 화이트리스트 구성
- 상태: **완료**

## Supabase — Postgres 직접 연결 (Phase 1, LangGraph checkpointer)

- [x] Supabase 대시보드 Project Settings → Database → Connection string(Session pooler)에서 발급 → `backend/.env`의 `SUPABASE_DB_URL`에 입력
- [x] `infra/supabase/migrations/0002_phase1.sql` 실행 (approvals.thread_id 컬럼 추가)
- 상태: **완료** — 실제 Postgres checkpointer 초기화 및 end-to-end 테스트 성공

## AI 모델 API ([ARCHITECTURE.md §7](./ARCHITECTURE.md#7-ai-모델-provider-전략) 참고)

특정 벤더에 고정하지 않고 provider 어댑터로 분리.

- [x] **Anthropic (Claude)** — 1순위는 로컬에 이미 로그인된 **Claude Code CLI**(구독 플랜)를 서브프로세스로 호출, 한도 초과/실패 시에만 API로 폴백(ARCHITECTURE.md §7.1). CLI만으로 Phase 1 실사용 테스트 완료 — `ANTHROPIC_API_KEY`는 폴백용 안전장치라 당장 급하지 않음(있으면 좋음). 상태: **CLI로 사용중, API 키는 선택사항**
- [x] **OpenAI** — 이미지(DALL-E) 생성 + RAG 임베딩(`text-embedding-3-small`)에 사용. `OPENAI_API_KEY` 발급 완료(`.env`에 반영됨). RAG 임베딩은 이미 실제 키로 문서 업로드→검색까지 검증 완료(Phase 4). 이미지 생성은 아직 `IMAGE_PROVIDER=mock` 상태 — `.env`에서 `IMAGE_PROVIDER=dalle`로 바꾸면 실제 DALL-E 호출 가능(아직 실사용 테스트 전).
- 영상(Sora) 생성 옵션은 미착수(Phase 3/4 범위 밖).
- [ ] **Google Gemini** — FinanceWorker 영수증 OCR(Vision) 기본값 + 이미지(Imagen)/영상(Veo) 생성 옵션. `GOOGLE_GEMINI_API_KEY` 발급 필요 (Google AI Studio). 상태: **코드 구현·모킹 검증 완료, 실제 키만 없음** — Phase 2 파이프라인(업로드→OCR→분개→승인→대시보드 반영) 전체가 실제 Supabase/텔레그램으로 검증됐고 Gemini 호출부만 모킹함. 키 발급 즉시 실사용 테스트 가능.
- 참고: 세 개 다 사용량/비용 한도 설정 권장.

## MCP 커넥터 ([ARCHITECTURE.md §6](./ARCHITECTURE.md#6-mcp-연동-외부-도구를-에이전트-툴로-노출) 참고)

- [ ] Canva — DesignWorker/MarketingWorker 크리에이티브 생성용, 상태: **미연동**
- [ ] Figma — DesignWorker/DevWorker 디자인-코드 연결용, 상태: **미연동**
- [ ] Google Calendar — PMWorker 일정 동기화용, 상태: **미연동**
- [ ] Google Drive — RAG 문서 소스 수집용, 상태: **미연동**
- [ ] Notion — PRD/WBS 문서 관리 및 RAG 소스, 상태: **미연동**
- [ ] Gmail — 보조 승인 알림 채널, 상태: **인증 필요** (claude.ai 커넥터 설정에서 사용자가 직접 인증해야 함, Claude Code가 대신 인증 불가)

---

**갱신 방법:** 각 항목의 체크박스와 "상태" 필드를 실제 진행에 맞춰 직접 수정. "미신청/미착수 → 신청함 → 승인대기 → 승인완료" 순서로 갱신한다.
