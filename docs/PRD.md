# CharisLab AI OS — PRD (제품 요구사항 정의서)

버전: v0.1 (초안) · 기반 문서: `CharisLab_AI_OS_Full_Spec_v4.pdf`, `claude.md`

## 1. 배경 및 목표

CharisLab은 대표(CEO) 1인 체제로 여러 제품을 동시에 운영한다. **실제 출시된 제품(2026-09-08 기준)**: ChaMu(iOS 전용, App Store id6801702365), SNAPTAIL(구 "SnapTale"/"아이 포토북", iOS id6760613767 · Android `com.charisro.snaptail`), 터치러쉬(iOS id6751933591 · Android `com.charisro.TouchRush`). 현재는 기획-개발-마케팅-회계 업무가 각 채널(문서, 메신저, 개별 툴)에 흩어져 있어 대표가 전체 현황을 한눈에 파악하기 어렵다.

**목표:** CEO의 지시 한 줄이 C-Level AI 임원진(CFO/CTO/CMO/CPO) 회의를 거쳐 실무 에이전트의 실제 작업(코드/포스팅/회계처리)으로 이어지고, 그 결과가 실시간 대시보드/캘린더로 시각화되며, 중요한 결정은 텔레그램으로 대표에게 최종 결재받는 **폐쇄형 AI 회사 운영체제**를 구축한다.

**성공 기준:** 대표가 별도 지시 없이도 "지시 → 진행 → 결재" 3단계만으로 하나의 제품 마케팅 캠페인/개발 태스크/회계 항목이 완결된다.

## 2. 사용자 / 페르소나

| 페르소나 | 설명 | 니즈 |
|---|---|---|
| CEO (쭈니) | 유일한 인간 의사결정권자, 자율적 위임 선호 | 최소 개입으로 전체 현황 파악 + 중요 결정만 승인 |
| C-Level 에이전트 (CFO/CTO/CMO/CPO/CDO/CSO) | Supervisor가 라우팅하는 LangGraph 노드 | CEO 지시를 구체 Task로 해석, 근거 데이터 기반 판단 |
| Worker 에이전트 (PM/Marketing/Design/Finance/Dev/신사업개발) | 실제 실행 담당 | 명확한 Task 정의, 필요한 도구(Tool/MCP) 접근권 |

## 3. 핵심 시나리오 (End-to-End)

1. CEO가 웹앱(또는 텔레그램)에 지시 입력 (예: "SnapTale 여름 프로모션 카드뉴스 만들어서 인스타에 올려")
2. Supervisor 노드가 현재 `schedule_progress`, `marketing_metrics_summary`를 참고해 CMO(Marketing Agent)로 라우팅
3. Marketing Agent가 상황(제품 특성, 채널, 캠페인 목적)에 맞춰 이미지 생성/영상 생성/카피라이팅/디자인 템플릿 등 **다양한 도구 중 적합한 것을 선택**해 콘텐츠 초안 제작(예: 정적 카드뉴스는 DALL-E+Canva MCP, 숏폼은 영상 생성 도구, 시안 디자인은 Figma/Canva MCP) → 초안을 텔레그램으로 CEO에게 전송해 승인 요청
4. CEO가 텔레그램에서 승인/반려/보완 지시
5. 승인 시 `PostToInstagram` 툴 실행 → 결과가 `marketing_metrics`에 초기값 기록
6. 이후 주기적으로 조회수/클릭률 수집 → Dashboard View 선그래프에 반영
7. 동시에 PM Agent가 이 캠페인을 Task로 등록해 Calendar View에 기간과 진행률 표시

## 4. 3대 뷰별 기능 요구사항

### Metaverse View
- Phaser.js 기반 2.5D 오피스 — 대표실/개발실/경영지원실 등 **부서(임원)별 룸**으로 구성, 각 룸에 책상 배치
- 각 C-Level/Worker 에이전트가 아바타로 표현되어 현재 활성 상태(회의중/작업중/대기) 시각적 표시
- 클릭 시 해당 에이전트의 최근 작업 로그 팝업
- **CEO가 직접 꾸밀 수 있는 에디터 제공** — 완전 자유배치보다는 룸 템플릿(크기/모양 선택) + 그리드 기반 책상 배치 방식으로, 적은 개발 공수로 커스터마이징 가능하게 함. **Phase 4에서 구현 완료**: 대표실/개발실/마케팅실/경영지원실 4개 룸(고정 템플릿) + 그리드 클릭으로 책상 추가/삭제. 룸 모양/크기 자체를 바꾸는 에디터는 아직 없음(고정 4룸), 필요해지면 후속 확장

### Calendar View
- 프로젝트/Task 단위 일정 표시 (FullCalendar 또는 react-big-calendar)
- WBS 하위 Task까지 드릴다운 가능
- Task 상태(To-Do/In Progress/Done)에 따른 색상 구분, 진행률(progress_pct) 표시

### Dashboard View
- 도넛 차트: 업무별 처리 현황 (부서별 Task 상태 분포)
- 선 그래프: 채널별 마케팅 지표 추이 (노출/클릭/전환)
- 막대 그래프: 현금 흐름 (매입/매출)
- 기간 필터(주/월/분기) 공통 제공

## 5. 에이전트별 R&R 및 성공지표

| 에이전트 | R&R | 성공지표(KPI) |
|---|---|---|
| PM (CPO) | 아이디어→PRD 작성, Task를 WBS로 분할, `schedules`/`tasks` 등록 | WBS 데드라인 준수율 |
| Marketing (CMO) | 제품별 홍보 콘텐츠(카드뉴스/숏폼/카피) 생성, 상황에 맞는 도구 선택(이미지/영상/디자인 생성 등), Instagram/Facebook/TikTok/Threads 직접 포스팅, 지표 수집 | 승인→포스팅 소요시간, 지표 수집 정확도 |
| Design (CDO) | 제품별 비주얼 아이덴티티/UI 시안 제작, 마케팅 크리에이티브(배너·썸네일·카드뉴스 디자인) 제작, Canva/Figma MCP를 활용한 디자인 산출물 생성 및 협업 | 디자인 승인까지 반려/보완 횟수, 브랜드 가이드 준수율 |
| Finance (CFO) | 영수증을 Gemini(Vision)로 OCR·인식→복식부기, 부가세/종소세 관리 | 분개 자동화 정확도, 결산 리드타임 |
| Dev/RAG (CTO) | 기획서 기반 코드 작성/PR(React Native, Flutter, PyQt5 등), **신규 앱은 Flutter로 개발 진행**, 전사 문서 RAG 검색 | PR 생성 성공률, 신규 앱 빌드 성공률, RAG 검색 정확도 |
| 신사업개발 (CSO) | 대표가 던진 아이디어를 입력받아 시장성/실현가능성 검토 후 사업 기획서(Lean Canvas/PRD 초안)로 구체화, PM Agent에게 실행 이관 | 아이디어→사업기획서 전환 리드타임, 실제 실행으로 채택된 비율 |

### 5.1 채널별 계정 운영 전략

- **Instagram/Facebook/TikTok 전부 통합 계정("CharisLab") 하나로 운영** (2026-08-26 결정 변경 — 기존엔 Instagram/Facebook만 제품별 개별 계정이었으나, 3개 제품 다 마케팅을 한 번도 하지 않아 팔로워 0에서 시작하는 상황이 TikTok 때와 동일해 같은 논리로 통합함). 팔로워 0에서 시작하는 여러 계정보다 하나에 집중해 알고리즘 노출을 빨리 확보하는 전략. 특정 제품이 충분히 성장하면 그때 개별 계정으로 분리 검토
- 이 결정에 따라 `MarketingWorker`는 채널·제품과 무관하게 항상 동일한 통합 계정(페이지/토큰)을 사용한다 — "제품→계정" 매핑 로직 불필요, 게시물 캡션에 제품명을 명시해 구분한다.

### 5.2 AI 모델 Provider 전략

특정 벤더(OpenAI 등)에 고정하지 않는다. 에이전트 추론은 Claude를 기본으로, 이미지/영상 생성은 상황에 따라 OpenAI·Google 중 선택, Finance(CFO) 에이전트의 영수증 OCR은 Google Gemini(Vision)를 기본값으로 사용한다 — 자세한 provider 매핑과 어댑터 설계는 [ARCHITECTURE.md §7](./ARCHITECTURE.md#7-ai-모델-provider-전략) 참고.

## 6. Human-in-the-Loop 정책

다음 액션은 **반드시** 텔레그램을 통한 CEO 최종 승인 후에만 실행한다:
- SNS 실계정 포스팅 (Mock 단계 제외)
- 광고 예산 집행/스케줄링
- 회계 분개의 최종 확정(장부 반영)
- 코드 PR의 main 브랜치 머지

승인/반려/보완 3가지 응답을 지원하며, "보완" 시 원래 에이전트에게 피드백과 함께 재작업 지시가 돌아간다.

## 7. 비기능 요구사항

- **인증:** Google OAuth 기반 폐쇄형 접근 (charislab.kr/operation 하위, 화이트리스트 이메일만 허용)
- **보안:** 외부 API 키는 서버 사이드에서만 보관, 클라이언트 노출 금지
- **감사추적:** 모든 에이전트 실행/승인 이력을 `agent_runs`, `approvals` 테이블에 기록
- **모바일 웹 지원:** Dashboard/Calendar View는 반응형, Metaverse View는 데스크톱 우선(모바일은 축소 뷰)

## 8. Out-of-Scope (v0.1)

- **SyncDay**: 기획서에 언급되었으나 현재 파일시스템/코드베이스에 실체가 없는 제품 — 향후 확장 대상으로만 표시, 이번 버전 마케팅 자동화 대상에서 제외
- 다중 CEO/조직 계정 지원 (현재는 대표 1인 체제 전제)
- TikTok 실연동 (개발자 심사 완료 전까지 Mock으로 대체, [[PHASE_PLAN]] 참고)
