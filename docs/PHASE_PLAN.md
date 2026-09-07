# CharisLab AI OS — 단계별(Phase) 실행 플랜

버전: v0.1 (초안) · 관련 문서: [PRD.md](./PRD.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [EXTERNAL_APIS.md](./EXTERNAL_APIS.md)

## 설계 원칙

외부 API(Meta Graph API, Threads API, TikTok API)는 앱 심사에 시간이 걸린다(Meta 통상 1~4주, TikTok은 더 보수적/장기간 가능; Threads는 같은 Meta 앱에 속하지만 별도 권한 심사 필요). 단, 본인 소유 계정만 대상으로 한다면 각 권한의 **Standard Access**(앱 Admin/Tester로 등록된 계정 한정 즉시 사용 가능)로 심사 없이 시작할 수 있다 — [EXTERNAL_APIS.md](./EXTERNAL_APIS.md) 참고. 이 병목이 전체 일정을 막지 않도록:

1. **Phase 0에서 Meta/Threads/TikTok 개발자 신청을 최우선으로 접수**해 대기시간을 확보하고
2. 승인 대기 중에는 [ARCHITECTURE.md의 Mock 어댑터 패턴](./ARCHITECTURE.md#5-mock--실연동-스위치-패턴)으로 나머지 기능을 끝까지 개발/검증한다.
3. 텔레그램 봇은 즉시 발급 가능하므로 Human-in-the-Loop 승인 흐름은 Phase 1부터 실제로 동작시킨다.

각 Phase는 이전 Phase의 State/DB 위에 누적된다.

---

## Phase 0 — 기반 셋업

**목표:** 아무 기능 없어도 되지만, 인증/DB/외부 연동 신청까지 "배관"을 전부 연결한다.

**핵심 산출물:**
- Supabase 프로젝트 생성 + [ARCHITECTURE.md DB 스키마](./ARCHITECTURE.md#3-supabase-db-스키마-초안) 마이그레이션 적용
- Google OAuth 연동 (charislab.kr/operation 화이트리스트 로그인)
- 텔레그램 봇 생성 + webhook 엔드포인트 확보
- **Meta 개발자 계정 + 앱 등록 + 권한 심사 신청 제출** ([EXTERNAL_APIS.md](./EXTERNAL_APIS.md) 체크리스트 갱신)
- **TikTok 개발자 계정 + 앱 신청 제출**
- 모노레포 스캐폴딩 (frontend/backend 빈 프로젝트, docker-compose)

**완료 기준(DoD):**
- [ ] Google 계정으로 로그인 가능한 빈 셸 앱이 배포됨
- [ ] 텔레그램 봇에 메시지 보내면 왕복 확인 가능
- [ ] Meta/TikTok 앱 심사 신청 접수 완료 (승인 여부와 무관, "제출"이 기준)
- [ ] Supabase 테이블 전체 생성 확인

---

## Phase 1 — 코어 오케스트레이션 MVP

**목표:** CEO 지시 하나가 실제로 Supervisor→PM Worker를 거쳐 Calendar에 반영되고, 텔레그램 승인이 실제로 동작한다.

**핵심 산출물:**
- FastAPI + LangGraph 최소 그래프: `Supervisor` + `PMWorker` + `BizDevWorker`(신사업개발) + `HumanApprovalNode`
- 기본 추론 엔진으로 **Claude**를 연결 — Claude Code CLI(구독 플랜) 1순위, Anthropic API 2순위 폴백 (`tools/ai/llm/`, ARCHITECTURE.md §7.1 참고)
- `tasks`/`schedules` CRUD API
- Calendar View 프론트엔드 연동, Google Calendar MCP 연동(외부 일정 동기화)

**완료 기준(DoD):**
- [x] CEO가 일반 텍스트 지시를 입력하면 PM Agent가 WBS 생성 — **실제 Claude CLI로 검증 완료**: "SnapTale에 육아일기 자동요약 기능 추가" 지시를 11개 하위 작업(부서·담당자·일정 포함)으로 정확히 분할함
- [x] CEO가 사업 아이디어를 던지면 BizDev Agent가 사업기획서 초안을 만들고 PM Agent가 WBS로 분할 (BizDev 경로) — 코드 구현 완료, mock으로 라우팅 검증 완료(실제 CLI로는 PM 직행 경로만 실측, BizDev 경로는 실제 승인 흐름에서 추가 확인 권장)
- [x] 생성된 Task가 Calendar View에 기간과 함께 표시됨 — FullCalendar 연동 완료 (빈 상태로 렌더 확인, 실제 DB 연동 확인은 아래 실사용 테스트에서)
- [x] Task 승인 요청이 텔레그램으로 전송되고 승인/반려/보완 응답이 그래프 재개로 이어짐 — interrupt/resume 메커니즘(승인/보완 루프 포함) mock DB로 검증 완료
- [x] **DB 연결 실사용 테스트 완료** — 실제 Supabase(Postgres checkpointer 포함)로 `POST /directives`→WBS 생성→실제 task/schedule insert→실제 텔레그램 메시지 발송→승인 콜백→`approved` 상태 전환까지 전부 실측 확인(테스트 데이터는 확인 후 정리함)
- [x] 승인/반려/보완 처리 후 텔레그램 **원본 카드를 그 자리에서 수정**(제목/작업목록 유지, 버튼 제거, 하단 문구를 "✅ 승인 처리됨" 등으로 교체)해 한 메시지로 결과가 보이게 함 (`acknowledge_decision`, `approvals.payload` 컬럼에 원본 카드 내용 저장) — 실제 텔레그램으로 검증 완료

---

## Phase 2 — Dashboard + Finance Agent

**목표:** 영수증 한 장이 실제 분개로 이어지고 대시보드에 즉시 반영된다.

**핵심 산출물:**
- 영수증 업로드 + **Gemini(Vision)** 기반 OCR 파이프라인 (`tools/ai/vision/gemini_ocr.py`) — LangGraph 그래프가 아니라 단순 동기 파이프라인으로 구현(선형 흐름이라 interrupt/checkpointer가 불필요, 대신 Phase 1의 `approvals`+텔레그램 인프라를 재사용)
- `FinanceWorker`(`app/workers/finance_worker.py`, 순수 함수) — 카테고리→계정과목 매핑 → `finance_entries` 저장(`status='draft'`)
- 승인 라우팅을 `task_plan`/`finance_entry` 공용으로 일반화(`callback_data="{target_type}:{id}:{decision}"`), finance는 승인/반려 2버튼(보완 없음)
- Dashboard View: 도넛 차트(업무 현황), 막대 그래프(현금 흐름), 영수증 업로드 폼

**완료 기준(DoD):**
- [x] 영수증 이미지 업로드 → OCR → 자동 분개 생성 — **실제 Supabase Storage/DB/텔레그램으로 검증 완료**(Gemini 호출만 모킹, `GOOGLE_GEMINI_API_KEY` 미발급 상태라 실제 Vision 호출은 키 발급 후 확인 필요)
- [x] 분개 결과가 Dashboard 막대 그래프에 즉시 반영 — `status='confirmed'`(텔레그램 승인 후)만 집계되도록 구현, 실제 확인
- [x] 부가세 대상 여부(`vat_flag`) 자동 판별 — Gemini 출력 필드로 반영(실제 Vision 응답으로는 미검증)
- [x] task_plan 승인 흐름이 callback_data 형식 변경 후에도 정상 동작 (회귀 테스트 완료)
- [ ] **실제 영수증 사진으로 Gemini Vision 실사용 테스트** — `GOOGLE_GEMINI_API_KEY` 발급 후 진행

---

## Phase 3 — Marketing Agent (Mock 우선)

**목표:** 콘텐츠 생성부터 승인, (Mock)포스팅, 지표 반영까지 전체 파이프라인을 Meta/TikTok 승인 여부와 무관하게 완성한다.

**핵심 산출물:**
- `MarketingWorker` — CEO 지시(Supervisor가 3-way 라우팅: bizdev/pm/marketing)에서 product/channel/caption/image_prompt를 구조화 추출, 이미지 생성(DALL-E, `IMAGE_PROVIDER` 미고정) 호출
- `PostToInstagram`/`PostToTikTok`/`PostToThreads` 툴 — 기본은 Mock 어댑터(`app/tools/social/`), 환경변수로 실연동 전환 가능
- `PublishWorker` — 승인된 콘텐츠를 포스팅하고 `marketing_metrics`에 지표 기록(Mock 단계에선 그럴듯한 더미 값)
- 승인 라우팅을 `task_plan`/`finance_entry`/`marketing_post` 3종 공용으로 일반화
- Dashboard View: 선 그래프(채널별 마케팅 지표 추이)
- **범위 조정(구현 중 결정):** DesignWorker의 Canva/Figma MCP 연동은 이번 Phase에서 제외 — Canva/Figma MCP는 Claude Code 세션 전용 커넥터라 독립 실행되는 FastAPI 백엔드가 직접 호출하기 어려움(별도 MCP 클라이언트 구현 필요, 범위 급증). 실제 크리에이티브 제작은 MarketingWorker의 이미지 생성으로 대체하고, Canva/Figma 연동은 이후 Phase로 미룸.

**완료 기준(DoD):**
- [x] 제품 지정 → Claude가 상황에 맞는 채널/카피/이미지 프롬프트를 자동 추출 — **실제 Claude CLI로 검증**: "SnapTale 여름 프로모션 카드뉴스 만들어서 인스타그램에 올려줘" → 실제 인스타그램용 카피(해시태그 포함) 자동 생성 확인
- [x] 텔레그램 최종 승인 → (Mock) 포스팅 처리 — 실제 텔레그램 카드(승인/반려 2버튼) 전송 및 콜백 재현으로 검증
- [x] `marketing_metrics`에 기록되고 Dashboard 선그래프에 반영 — 실제 Supabase insert 확인, Dashboard 채널별 라인차트 렌더 확인
- [x] task_plan(Phase 1)/finance_entry(Phase 2) 승인 흐름이 라우팅 일반화 이후에도 정상 동작 (회귀 테스트 완료)
- [ ] Meta(Instagram/Facebook)/Threads 승인이 이 시점까지 완료됐다면 `SOCIAL_ADAPTER=meta`(또는 `threads`)로 전환해 실포스팅 1건 검증
- [ ] **실제 이미지 생성 테스트** — `OPENAI_API_KEY` 발급 후 `IMAGE_PROVIDER=dalle`로 전환해 실제 DALL-E 호출 확인 (현재는 `IMAGE_PROVIDER=mock` 기본값으로 플레이스홀더 이미지 사용중)

---

## Phase 4 — Metaverse View + Dev/RAG Agent

**목표:** 시각적 완성도(메타버스)와 지식 관리(RAG), 개발 에이전트를 채운다.

**핵심 산출물:**
- Phaser.js 2.5D 오피스(대표실/개발실/경영지원실/마케팅실 4개 룸, 룸 템플릿 고정 + 그리드 기반 책상 배치 편집) + 에이전트 활동 상태 표시
- pgvector 기반 RAG 검색 — 문서 업로드는 수동(`POST /documents`)으로 시작, OpenAI 임베딩 사용. Google Drive/Notion MCP 자동 수집은 이번 Phase 범위 밖(연동 안 된 상태, EXTERNAL_APIS.md 참고)
- `DevWorker` — RAG로 관련 문서를 찾아 컨텍스트로 활용해 코드 변경 제안/PR 초안을 **텍스트로만** 생성
- `agent_runs` 최초 실사용 — Supervisor/BizDev/PM/Marketing/DevWorker 실행을 기록해 Metaverse 활동 상태의 근거로 사용
- **범위 조정(구현 중 결정, 사용자 확인):** Dev Agent는 이번 Phase에서 sping/SNAPTAIL/spingkids 같은 실제 제품 저장소에 파일을 쓰거나 PR을 만들지 않는다 — 위험도가 높아 코드 제안 텍스트 생성까지만 구현. 실제 저장소 쓰기 권한은 신뢰도 검증 후 별도 Phase.

**완료 기준(DoD):**
- [x] RAG: 문서 업로드 → 벡터화 → 자연어 검색으로 재조회 — **실제 OpenAI 임베딩 + pgvector로 검증 완료**
- [x] Dev Agent가 RAG 검색 결과를 실제로 참고해 코드 제안(제목/요약/영향 파일/의사코드/PR 초안)을 생성 — 실제 Claude CLI로 검증, 스스로 "실제 저장소 접근 권한 없어 파일 경로는 추정"이라고 명시함
- [x] 에이전트 활동 상태 표시 — `agent_runs` 계측 + `/agents/status`로 실제 실행 기록 반영 확인
- [x] Metaverse 오피스에 룸 4개 표시 + 그리드 클릭으로 책상 추가/제거 가능 (`/office/desks` CRUD 실제 검증)
- [x] task_plan/finance_entry/marketing_post 승인 흐름이 dev_proposal 추가 이후에도 정상 동작 (회귀 테스트 완료)
- [ ] Flutter 기반 실제 코드/PR 생성 — 범위 조정으로 이번 Phase에서는 제외(위 참고)

---

## Phase 5 — 실연동 확장 및 하드닝 (지속)

**목표:** Mock을 실제 서비스로 전환하고 운영 신뢰성을 높인다.

**핵심 산출물:**
- Meta/TikTok 승인 완료 시 어댑터를 실연동으로 전환, 실포스팅 정식 운영
- Google Analytics 연동 (GA4)
- 감사로그/권한 강화 (`agent_runs`, `approvals` 기반 리포트)
- 부가세/종소세 리포트 자동화

**완료 기준(DoD):**
- [ ] 모든 SNS 포스팅이 Mock 없이 실제 계정으로 집행됨
- [ ] GA 지표가 `marketing_metrics`와 교차 검증됨
- [ ] 분기별 부가세 신고 자료 자동 생성
- [x] **Goal형 병렬 실행 전환** — 레퍼런스 서비스 Humant의 "Goal" 기능을 참고해, CEO 지시 하나에 여러 부서가 필요하면 LangGraph에서 실제로 병렬 fan-out하도록 Supervisor/승인 흐름을 재설계. 실제 지시("SnapTale 여름 프로모션 콘텐츠 만들면서 동시에 캘린더 동기화 버그도 개발팀에서 검토해줘")로 marketing+dev 두 Worker가 실제 겹치는 시간대에 실행되고, 텔레그램 카드 2장이 각각 독립적으로(하나만 승인해도 다른 하나는 대기 유지) 처리되는 것까지 실측 검증 완료(테스트 데이터 정리함). 단일 부서 지시 회귀도 확인. 자세한 설계는 ARCHITECTURE.md §2.1
- [x] **감사로그/권한 강화** — 코드 확인 결과 백엔드 API가 사실상 인증 없이 열려있던 것을 발견(구글 로그인은 화면 진입만 막고 이후 API 호출엔 검증이 없었음). 서버 발급 세션 토큰(JWT, `SESSION_SECRET`) 도입 + `health`/`auth`/`telegram` 제외 전 라우터에 `Depends(require_ceo)` 적용, WebSocket(`/agents/ws`)은 쿼리파라미터 토큰으로 별도 검증 — **실제로 토큰 없이 401, 유효 토큰으로 200/WS 연결 성공까지 검증 완료**. 텔레그램 webhook은 `secret_token` 검증 코드까지 구현(실제 등록은 배포 후, EXTERNAL_APIS.md 참고). `GET /audit/log`(agent_runs+approvals 통합) + Dashboard 표시까지 구현, 실제 CEO 지시 1건으로 감사로그에 반영되는 것까지 확인(테스트 데이터는 정리함). 자세한 설계는 ARCHITECTURE.md §8 참고

---

## 다음 액션

Phase 0을 시작하려면: (1) Supabase 프로젝트 생성, (2) Meta/TikTok 개발자 신청 접수, (3) 텔레그램 봇 생성 — 이 세 가지는 대기시간이 있으므로 최우선으로 착수하는 것을 권장한다. [EXTERNAL_APIS.md](./EXTERNAL_APIS.md)에서 신청 현황을 계속 추적한다.
