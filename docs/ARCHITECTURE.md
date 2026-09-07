# CharisLab AI OS — 아키텍처 문서

버전: v0.1 (초안) · 관련 문서: [PRD.md](./PRD.md), [PHASE_PLAN.md](./PHASE_PLAN.md), [EXTERNAL_APIS.md](./EXTERNAL_APIS.md)

## 1. 전체 구성도

```
┌─────────────────────────────────────────────────┐
│  React + Vite SPA  (charislab.kr/operation)      │
│  ┌───────────┐ ┌───────────┐ ┌───────────────┐   │
│  │Metaverse  │ │ Calendar  │ │  Dashboard    │   │
│  │(Phaser.js)│ │(FullCal.) │ │ (Recharts)    │   │
│  └───────────┘ └───────────┘ └───────────────┘   │
└───────────────────────┬───────────────────────────┘
                         │ REST + WebSocket/SSE
┌───────────────────────▼───────────────────────────┐
│  FastAPI (Python)                                  │
│  ┌─────────────────────────────────────────────┐  │
│  │  LangGraph 오케스트레이션                     │  │
│  │  Supervisor(C-Level) → Worker Agents         │  │
│  └─────────────────────────────────────────────┘  │
└───┬───────────┬───────────┬───────────┬───────────┘
    │           │           │           │
┌───▼───┐  ┌────▼────┐ ┌────▼────┐ ┌────▼─────────┐
│Supabase│  │Meta/    │ │Telegram │ │ AI Model APIs│
│Postgres│  │TikTok/GA│ │Bot      │ │ Claude/OpenAI│
│pgvector│  │API      │ │(승인)    │ │ /Gemini      │
│Storage │  │         │ │         │ │ (§7 참고)     │
└────────┘  └─────────┘ └─────────┘ └──────────────┘
```

## 2. LangGraph 그래프 설계

### 노드 구조
- **Supervisor (C-Level Router)**: CEO 지시와 State의 `schedule_progress`, `marketing_metrics_summary`를 근거로 CFO/CTO/CMO/CPO/CDO/CSO 중 어디로 라우팅할지 판단
- **Worker 서브그래프**: 부서별로 독립된 서브그래프
  - `PMWorker` — PRD 초안 작성, WBS 분할, `tasks`/`schedules` upsert
  - `MarketingWorker` — CEO 지시에서 product/channel/caption/image_prompt를 구조화 추출 → 이미지 생성 provider 호출 → `HumanApprovalNode`로 이동. **구현 노트(Phase 3):** Canva/Figma MCP는 Claude Code 세션 전용 커넥터라 독립 FastAPI 백엔드에서 직접 호출하기 어려워 이번 Phase에서 제외 — 실제 크리에이티브는 이미지 생성 provider(DALL-E, `IMAGE_PROVIDER` 미고정)로 대체. DesignWorker/Canva·Figma 연동은 별도 MCP 클라이언트 구현이 필요해 이후 Phase로 미룸
  - `PublishWorker` — 승인된 마케팅 콘텐츠를 `PostToInstagram`/`PostToTikTok`/`PostToThreads` 툴(`app/tools/social/`)로 게시 → `marketing_metrics`에 지표 기록(Mock 단계에선 더미 값)
  - `FinanceWorker` — 영수증 이미지를 **Gemini(Vision)**로 OCR·항목 인식 → 복식부기 분개 생성 (§7 참고). **구현 노트(Phase 2):** 이건 LangGraph 노드가 아니라 `app/workers/finance_worker.py`의 순수 함수로 구현됨 — 입력이 CEO 텍스트 지시가 아니라 파일 업로드이고 흐름이 "OCR→매핑→승인" 선형이라 분기/재작업이 없어 interrupt/checkpointer가 불필요했음. 승인은 Phase 1의 `approvals` 테이블+텔레그램 인프라를 `target_type='finance_entry'`로 재사용(`POST /finance/receipts` → 직접 승인 카드 전송 → webhook이 그래프 resume 없이 `finance_entries.status`만 갱신)
  - `DevWorker` — RAG로 관련 문서 검색 → Claude로 코드 변경 제안(제목/요약/영향 파일/의사코드/PR 초안) 생성. **구현 노트(Phase 4):** 실제 git 저장소에 파일을 쓰거나 PR을 생성하지 않는다 — sping/SNAPTAIL/spingkids 같은 실제 운영 제품 저장소에 자동으로 코드를 쓰는 건 위험도가 높아, 신뢰도 검증 전까지는 텍스트 제안만 생성하고 사람이 직접 반영한다(신규 앱 Flutter 개발 등 실제 파일시스템 접근은 이후 Phase)
  - `BizDevWorker` (신사업개발/CSO) — CEO 아이디어 인풋 → 시장성 검토 → 사업기획서 초안 → PMWorker에 실행 이관
- **HumanApprovalNode**: LangGraph `interrupt()`로 그래프 실행을 일시정지하고 텔레그램 webhook 응답을 대기. 승인/반려/보완 3분기 처리 후 재개.

> **구현 현황(Phase 1~4):** `Supervisor`(bizdev/pm/marketing/dev 4분기) → `BizDevWorker`/`MarketingWorker`/`DevWorker` → `PMWorker`/`HumanApprovalNode` → (marketing 승인 시) `PublishWorker`까지 구현·검증 완료(`backend/app/graphs/`). `HumanApprovalNode`는 `task_plan`/`finance_entry`/`marketing_post`/`dev_proposal` 4종 승인을 공용 인프라(`approvals` 테이블 + 텔레그램 카드, `callback_data="{target_type}:{id}:{decision}"`)로 처리한다 — finance_entry만 그래프 밖에서 직접 처리(§2 FinanceWorker 노트 참고), 나머지 셋은 그래프 resume. `task_plan`/`dev_proposal`은 3버튼(승인/보완/반려, 보완 시 해당 Worker로 재진입), `finance_entry`/`marketing_post`는 2버튼(승인/반려). Checkpointer는 `AsyncPostgresSaver.from_conn_string()`(단일 커넥션, `AsyncExitStack`으로 앱 lifespan 동안 유지)을 사용 — `SUPABASE_DB_URL`(REST service-role과 별개의 Postgres 직접 연결) 필요. `agent_runs`는 Phase 4에서 최초로 연결(모든 Worker 시작/종료 시 insert/update) — Metaverse View의 활동 상태 표시(§4 이하) 근거로 사용. Design Worker와 전체 C-Level(CFO/CDO) 라우팅은 이후 Phase에서 추가된다.

### 2.1 Goal형 병렬 실행 (레퍼런스: Humant의 "Goal" 기능)

`Supervisor`는 단순 라우터가 아니라 **킥오프 판단**을 겸한다 — CEO 지시 하나에 여러 부서가 동시에 필요하면(`GoalPlan.routes`가 2개 이상) 해당 Worker들을 **같은 슈퍼스텝에서 병렬 실행**하고, 부서별 브리핑(`worker_briefs`)까지 함께 생성해 각 Worker에게 전달한다. 단순 지시는 여전히 부서 1개만 골라 기존과 동일하게 순차 동작(하위 호환).

- **병렬 실행 메커니즘**: `route_after_supervisor`가 노드 이름 **리스트**를 반환하면 LangGraph가 해당 노드들을 같은 슈퍼스텝에서 동시 실행한다(`bizdev`가 선택되면 `pm`은 자동으로 그 뒤에 이어지므로 목록에서 제외).
- **승인 노드는 Worker별로 분리**: `pm_approval`/`marketing_approval`/`dev_approval` 3개를 따로 둔다(`app/graphs/human_approval.py`의 `make_approval_node(kind)`). 공유 노드 하나를 쓰면 두 Worker가 같은 슈퍼스텝에서 동시에 그 노드로 들어올 때 LangGraph가 "여러 선행자를 기다리는 조인(join)"으로 취급해 상태가 섞여버려 어떤 Worker의 결과인지 구분이 안 된다 — 실제로 겪은 함정.
- **독립적인 텔레그램 승인**: 병렬 실행 중인 Worker마다 `interrupt()`가 별도로 발생하고(`result["__interrupt__"]`가 리스트), 각 `Interrupt`는 고유 `id`를 가진다. `approvals.interrupt_id`(migration `0007`)에 저장해두고, 재개할 땐 `Command(resume={interrupt_id: value})`로 **그 카드에 해당하는 interrupt만** 골라 재개한다 — 나머지는 그대로 대기 유지(`app/api/directives.py`가 여러 interrupt를 순회하며 카드를 각각 보내고, `app/api/telegram.py`의 `_handle_graph_resume`이 approval 행에 저장된 `interrupt_id`로 재개한다).
- **state reducer 필수**: `messages`(여러 Worker가 같은 슈퍼스텝에 동시에 씀)와 `decisions`(재개 시 이미 완료된 다른 승인 노드가 캐시된 값으로 같은 틱에 재확정되며 같이 쓸 수 있음) 둘 다 reducer(`Annotated[..., operator.add]` / 커스텀 dict 병합)가 없으면 `InvalidUpdateError`가 난다 — 실제로 겪고 고침(`app/graphs/state.py`).
- **CLI 동시 호출 이슈**: 여러 Worker가 동시에 LLM을 호출하면서 `claude` CLI 서브프로세스 2개를 진짜로 동시에 띄우면 간헐적으로 stdout에 다른 프로세스의 응답이 섞여 파싱 오류가 나는 걸 실측으로 재현함 — `app/tools/ai/llm/claude_cli.py`에 `asyncio.Semaphore(1)`을 둬서 Worker 실행 자체는 병렬로 두되 CLI 서브프로세스 호출만 한 번에 하나씩 순서대로 실행하도록 고침. (겸사겸사 Anthropic API 폴백 경로(`claude.py`)의 `temperature` 파라미터가 최신 모델에서 400 에러를 내던 것도 이번에 발견해 제거함 — CLI가 드물게 실패했을 때 폴백마저 죽던 버그.)
- Metaverse View는 동시에 활성화되는 여러 Worker가 회의실 좌석(`GUEST_SEATS`, 4개)에 겹치지 않게 배정된다(`OfficeScene.ts`).

### State 스키마 (TypedDict)

```python
class OSState(TypedDict, total=False):
    ceo_directive: str
    active_departments: list[str]              # Supervisor가 고른 부서들(1개 이상)
    worker_briefs: dict[str, str]               # 부서별 킥오프 브리핑
    biz_plan: dict
    biz_plan_brief: str
    wbs_plan: dict
    marketing_post: dict
    dev_proposal: dict
    decisions: Annotated[dict[str, str], _merge_dicts]  # 부서별 승인 결과 - 병렬 승인이 안 섞이게
    pending_approvals: list[dict]
    schedule_progress: dict                     # PM Worker가 갱신, Supervisor 라우팅 근거
    marketing_metrics_summary: dict             # Marketing Worker가 갱신, Supervisor 라우팅 근거
    messages: Annotated[list[dict], operator.add]  # 병렬 동시쓰기 허용
```

`schedule_progress`와 `marketing_metrics_summary`를 State에 상시 포함시켜, Supervisor가 "지금 마케팅 지표가 저조하니 CMO 우선순위를 높인다" 같은 데이터 기반 판단을 하도록 한다 (claude.md 3번 지침 반영).

## 3. Supabase DB 스키마 초안

```sql
-- 업무/일정
create table tasks (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  status text check (status in ('todo','in_progress','done')) default 'todo',
  dept text not null,                 -- 'CFO'|'CTO'|'CMO'|'CPO'|'CDO'|'CSO'
  assignee_agent text not null,
  start_date date,
  end_date date,
  wbs_parent_id uuid references tasks(id),
  progress_pct int default 0,
  created_at timestamptz default now()
);

create table schedules (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null,
  task_id uuid references tasks(id),
  calendar_start timestamptz,
  calendar_end timestamptz
);

-- 마케팅
create table marketing_metrics (
  id uuid primary key default gen_random_uuid(),
  product text not null,              -- 'SPING'|'SnapTale'|...
  channel text not null,               -- 'instagram'|'facebook'|'tiktok'|'threads'
  metric_date date not null,
  impressions int default 0,
  clicks int default 0,
  conversions int default 0,
  post_id text
);

-- RAG 문서
create extension if not exists vector;
create table documents (
  id uuid primary key default gen_random_uuid(),
  title text,
  source_path text,
  created_at timestamptz default now()
);
create table document_embeddings (
  id uuid primary key default gen_random_uuid(),
  document_id uuid references documents(id),
  content text,
  embedding vector(1536)
);

-- 재무
create table finance_entries (
  id uuid primary key default gen_random_uuid(),
  entry_date date not null,
  debit_account text not null,
  credit_account text not null,
  amount numeric not null,
  category text,
  vat_flag boolean default false,
  receipt_url text,
  status text check (status in ('draft','confirmed','rejected')) default 'draft',  -- 0004: 텔레그램 승인 전(draft)/후(confirmed) 구분
  created_at timestamptz default now(),
  merchant text,
  raw_ocr jsonb                        -- Gemini Vision 원본 응답 보관(디버깅/재처리용)
);

-- 승인/감사
create table approvals (
  id uuid primary key default gen_random_uuid(),
  target_type text not null,           -- 'marketing_post'|'finance_entry'|'pr_merge'
  target_id uuid,
  telegram_msg_id text,
  status text check (status in ('pending','approved','rejected','revision')) default 'pending',
  created_at timestamptz default now(),
  thread_id text,                      -- 0002: LangGraph 실행 단위 추적
  payload jsonb                        -- 0003: 원본 승인 카드 내용(제목/작업목록) — 처리 후 같은 메시지에 결과를 합치기 위해 보관
);

create table agent_runs (
  id uuid primary key default gen_random_uuid(),
  agent_name text not null,
  input jsonb,
  output jsonb,
  started_at timestamptz default now(),
  finished_at timestamptz
);

-- Metaverse 사무실 (Phase 4) — 룸은 프론트 고정 템플릿, 책상 배치만 영속화
create table office_desks (
  id uuid primary key default gen_random_uuid(),
  room text not null,          -- '대표실'|'개발실'|'마케팅실'|'경영지원실'
  grid_x int not null,
  grid_y int not null,
  dept text,
  label text,                  -- 표시용 이름 (예: 'PM Agent')
  created_at timestamptz default now(),
  unique (room, grid_x, grid_y)
);

-- RAG 벡터 검색 (Phase 4) — Supabase REST는 벡터 유사도 검색을 직접 지원하지 않아 Postgres 함수로 노출
create or replace function match_documents(query_embedding vector(1536), match_count int default 5)
returns table (id uuid, document_id uuid, content text, similarity float)
language sql stable as $$
  select document_embeddings.id, document_embeddings.document_id, document_embeddings.content,
         1 - (document_embeddings.embedding <=> query_embedding) as similarity
  from document_embeddings
  order by document_embeddings.embedding <=> query_embedding
  limit match_count;
$$;
```

## 4. 모노레포 폴더 구조

```
operation/
  docs/                          # PRD, 아키텍처, 플랜
  frontend/
    src/
      views/
        Metaverse/
          MetaverseView.tsx       # Phase 4: Phaser.Game 마운트 + React 상태(desks/agentStatus) 연동, 책상 추가/삭제 모달
          OfficeScene.ts          # Phase 4: Phaser.Scene — 룸 4개(고정 템플릿) 렌더링, 그리드 클릭 히트테스트
        Calendar/                # FullCalendar 연동 완료 (Phase 1)
        Dashboard/                # 도넛/막대/선 그래프 (Phase 2~3)
      components/
        Sidebar.tsx
        DirectiveBar.tsx         # CEO 지시 입력바 (Phase 1)
      lib/                       # API client, Supabase client
  backend/
    app/
      graphs/                    # LangGraph 정의 (Phase 1~4)
        state.py                 # OSState TypedDict
        schemas.py               # RouteDecision/BizPlan/WBSPlan/MarketingPost/DevProposal 등 구조화 출력 스키마
        supervisor.py            # 4-way 라우팅(bizdev/pm/marketing/dev)
        human_approval.py        # interrupt() + 4종 target_type 공용 승인/반려/보완 라우팅
        build.py                 # 그래프 조립 + compile(checkpointer=...)
        workers/
          bizdev_worker.py
          pm_worker.py
          marketing_worker.py     # Phase 3: product/channel/caption/image_prompt 추출 + 이미지 생성
          publish_worker.py       # Phase 3: 승인된 콘텐츠 포스팅 + marketing_metrics 기록
          dev_worker.py           # Phase 4: RAG 검색 → 코드 제안(DevProposal) 생성, 실제 저장소 쓰기 없음
          (design_worker.py — 이후 Phase)
      workers/                     # LangGraph 노드가 아닌 독립 파이프라인용 워커
        finance_worker.py           # Phase 2: 영수증 OCR 결과 → 복식부기 계정 매핑(순수 함수)
        rag_worker.py                # Phase 4: chunk_text/rag_search — api/documents.py와 graphs/workers/dev_worker.py가 공유
      tools/
        social/                  # Phase 3 구현 완료
          base.py                # SocialPoster Protocol
          __init__.py            # get_social_poster(channel, product) 팩토리
          mock.py                # 기본값(SOCIAL_ADAPTER=mock)
          meta.py, tiktok.py, threads.py  # 실연동은 Phase 5에서 (현재는 NotImplementedError 스텁)
        ai/
          llm/
            base.py               # LLMProvider Protocol
            __init__.py           # get_llm() 팩토리 — CLI 1순위, API 2순위 폴백 (Phase 1 구현 완료, §7.1 참고)
            claude_cli.py          # 1순위: Claude Code CLI(구독 플랜) 서브프로세스 호출
            claude.py              # 2순위: Anthropic API(종량제, langchain-anthropic)
            openai.py             # (미착수)
            gemini.py             # (미착수)
          image/
            base.py               # ImageGenProvider Protocol
            __init__.py           # get_image_gen() 팩토리 (Phase 3 구현 완료)
            mock.py                # 기본값(IMAGE_PROVIDER=mock, OPENAI_API_KEY 발급 전까지)
            dalle.py               # OpenAI DALL-E 구현체 (코드 완료, 실제 키 있음 — 실사용 테스트 대기중)
          video/                  # (미착수) sora.py, veo.py
          vision/
            base.py               # VisionOCRProvider Protocol
            __init__.py           # get_vision_ocr() 팩토리 (Phase 2 구현 완료)
            gemini_ocr.py         # Gemini Vision 구현체 — 영수증 OCR (Phase 2 구현 완료, 실제 키만 미발급)
          embedding/
            base.py               # EmbeddingProvider Protocol
            __init__.py           # get_embedding() 팩토리 (Phase 4 구현 완료)
            openai_embedding.py   # text-embedding-3-small — RAG 문서/질의 벡터화, 실제 키로 검증 완료
        mcp/
          google_calendar.py      # 인터페이스만 정의, 비활성 (Phase 1)
        telegram_bot.py           # 승인 요청 전송/확인 — `target_type`(task_plan/finance_entry/marketing_post/dev_proposal)별로 카드 포맷·버튼 개수를 분기
      api/                       # FastAPI 라우터
        health.py, auth.py       # Phase 0
        tasks.py, schedules.py, directives.py, telegram.py  # Phase 1
        finance.py               # 영수증 업로드/조회/대시보드 집계 (Phase 2)
        marketing.py             # GET /marketing/metrics — Dashboard 선그래프용 (Phase 3)
        documents.py             # Phase 4: POST /documents(업로드+임베딩), GET /documents/search(RAG 검색)
        office.py                # Phase 4: GET/POST/DELETE /office/desks
        agents.py                # Phase 4: GET /agents/status — agent_runs 기반 활성/유휴 판정
      db/
        supabase_client.py       # REST(service-role) 클라이언트
        checkpointer.py          # Postgres 직접 연결 기반 LangGraph checkpointer
        agent_runs.py            # Phase 4: start_run/finish_run — 5개 Worker 노드가 공통 사용
  infra/
    docker-compose.yml
    supabase/
      migrations/
        0001_init.sql
        0002_phase1.sql          # approvals.thread_id 추가
        0003_approval_payload.sql # approvals.payload 추가 (텔레그램 확인 메시지를 한 메시지로 합치기 위함)
        0004_finance_status.sql   # finance_entries.status/created_at/merchant/raw_ocr 추가 (Phase 2)
        0005_rag_search.sql       # match_documents() pgvector 검색 함수 (Phase 4)
        0006_office_desks.sql     # office_desks 테이블 (Phase 4)
```

## 5. Mock ↔ 실연동 스위치 패턴

SNS 포스팅 도구는 인터페이스를 고정하고 어댑터만 교체 가능하게 설계한다:

```python
# app/tools/social/base.py
class SocialPoster(Protocol):
    async def post(self, content: PostContent) -> PostResult: ...

# 환경변수 SOCIAL_ADAPTER=mock|meta|tiktok|threads 로 런타임 선택
```

이렇게 하면 Meta/TikTok/Threads 앱 심사가 지연되어도 나머지 파이프라인(콘텐츠 생성 → 승인 → 지표 기록 → 대시보드)을 Mock으로 끝까지 검증할 수 있고, 승인이 나는 즉시 어댑터만 교체하면 된다.

## 6. MCP 연동 (외부 도구를 에이전트 툴로 노출)

각 에이전트가 직접 API를 처음부터 구현하기보다, 이미 연결 가능한 MCP 서버를 우선 활용한다. Worker별 매핑:

| MCP 서버 | 사용 에이전트 | 용도 |
|---|---|---|
| Canva | DesignWorker, MarketingWorker | 카드뉴스/배너/숏폼 썸네일 등 마케팅 크리에이티브 생성·편집 — **보류(Phase 3에서 확인됨):** Claude Code 세션 전용 커넥터라 독립 실행되는 FastAPI 백엔드가 직접 호출할 수 없다. 별도 MCP 클라이언트 구현+인증이 필요해 범위가 커서 이후 Phase로 미룸 |
| Figma | DesignWorker, DevWorker | UI/UX 시안 제작, 디자인-코드 연결(Code Connect) — Canva와 동일한 이유로 보류 |
| Google Calendar | PMWorker | CEO 개인/외부 캘린더와 Calendar View(`schedules`) 양방향 동기화 |
| Google Drive | RAG/DevWorker | 기획/개발/운영 문서 소스 자동 수집 → `documents`/`document_embeddings` 적재 — **미연동.** Phase 4는 `POST /documents` 수동 업로드로 RAG를 먼저 검증(실제 OpenAI 임베딩+pgvector 검색 동작 확인됨), 자동 수집은 이후 Phase |
| Notion | PMWorker, RAG | PRD/WBS 문서 관리 및 RAG 소스로 활용 — 미연동, 위와 동일 |
| Gmail | Supervisor/승인 알림 | 텔레그램 외 보조 알림 채널 (승인 요청/완료 통지) — **인증 필요, 미연동 상태** |

**설계 원칙**: MCP 도구는 LangGraph Worker 노드의 Tool 목록에 등록해 호출하며, Worker 로직은 "어떤 상황에 어떤 MCP/자체 툴을 쓸지"를 라우팅하는 역할까지 포함한다(예: MarketingWorker가 정적 이미지는 Canva MCP, 코드 연동 디자인은 Figma MCP를 선택). Gmail처럼 인증이 안 된 커넥터는 [EXTERNAL_APIS.md](./EXTERNAL_APIS.md)에서 상태를 추적하고, 인증 전까지는 텔레그램 단일 채널로 운영한다.

## 7. AI 모델 Provider 전략

특정 벤더에 고정하지 않고, SNS 포스팅 어댑터와 동일한 패턴(`Protocol` 인터페이스 + provider별 구현체 + 환경변수 스위치)으로 LLM/이미지/영상/비전 모델을 분리한다.

| 용도 | 기본 Provider | 사용처 | 선택 이유 |
|---|---|---|---|
| 추론(에이전트 두뇌) | **Claude — CLI 1순위, API 2순위 폴백** | Supervisor, PMWorker, DevWorker, BizDevWorker 등 대부분의 Worker | 복잡한 지시 이해·코드 생성·기획 문서 작성 품질이 강점 |
| 이미지 생성 | **Mock(기본)** → OpenAI DALL-E ↔ Google Imagen | MarketingWorker | 사실적 제품샷 vs 일러스트풍 등 스타일에 따라 상황별 선택. `SOCIAL_ADAPTER=mock`과 동일 철학. `OPENAI_API_KEY`는 이미 발급됨 — `IMAGE_PROVIDER=dalle`로 전환하면 실제 호출(아직 실사용 테스트 전) |
| 영상 생성 | OpenAI Sora ↔ Google Veo | MarketingWorker | 숏폼(TikTok/Reels) 콘텐츠용, 두 provider 다 아직 비용/큐 상황에 따라 스위칭 여지를 둠 |
| 비전(OCR) | **Google Gemini (Vision)** | FinanceWorker | 영수증 사진 인식에 필요한 비전 인식 정확도와, 여러 장을 한 번에 처리할 수 있는 대규모 컨텍스트 처리 능력이 강점 |
| 임베딩(RAG) | **OpenAI(`text-embedding-3-small`)** | DevWorker, `/documents` API | `document_embeddings.embedding vector(1536)`과 차원이 일치. 실제 키로 문서 업로드→검색까지 검증 완료(Phase 4) |

```python
# app/tools/ai/llm/base.py
class LLMProvider(Protocol):
    async def complete(self, messages: list[Message], **kwargs) -> str: ...

# app/tools/ai/vision/base.py
class VisionOCRProvider(Protocol):
    async def extract_receipt(self, image: bytes) -> ReceiptData: ...

# 환경변수 예: LLM_PROVIDER=claude, IMAGE_PROVIDER=dalle|imagen, VIDEO_PROVIDER=sora|veo
# FinanceWorker는 VISION_PROVIDER=gemini 로 고정(다른 옵션 필요 시에만 교체)
```

FinanceWorker의 영수증 OCR은 기본값을 Gemini로 고정해 구현하되, 인터페이스는 동일한 `VisionOCRProvider` 패턴을 따라 다른 벤더로 교체 가능하게 열어둔다.

### 7.1 Claude 추론 — CLI 우선, API 폴백

`LLM_PROVIDER=claude`일 때 `get_llm()`(`app/tools/ai/llm/__init__.py`)이 반환하는 `ClaudeCLIWithAPIFallback`은:

1. **1순위 — Claude Code CLI**(`claude -p ... --output-format json --json-schema ...`): 구독 플랜 사용량을 소진. `--tools ""`로 파일/Bash 접근을 막아 순수 추론 호출만 하고, `--json-schema`로 각 Worker의 Pydantic 스키마를 그대로 넘겨 `structured_output` 필드를 받는다(수동 JSON 파싱 불필요, 실측 확인됨).
2. **2순위 — Anthropic API**(`ClaudeLLMProvider`, `langchain-anthropic`): CLI가 실패하거나(`is_error`/`api_error_status` 존재, 실행 자체 실패, 타임아웃) 사용량 한도를 초과했을 때만 자동 전환.

**실사용 전제:** CLI는 그 서버에 `claude` 바이너리가 설치되어 있고 로그인(구독 인증)되어 있어야 동작한다. 로컬 개발 환경(이 컴퓨터)은 이미 로그인되어 있어 `ANTHROPIC_API_KEY` 없이도 Phase 1 전체가 실제로 동작함을 확인했다(WBS 생성 실측 테스트 완료). 이후 `charislab.kr`에 실제 배포할 서버에서는 `claude setup-token`(구독 기반 장기 인증 토큰)으로 헤드리스 인증을 해두거나, 그마저 안 되면 API 키만으로 폴백 동작한다.

## 8. 인증/세션 (Phase 5)

**구현 전 상태(문제):** `/auth/google`은 구글 ID 토큰을 검증해 화이트리스트 이메일인지만 확인하고 끝났다 — 세션을 발급하지 않았고, 프론트도 로그인 성공 시 화면만 전환할 뿐 이후 API 호출에 아무 인증 정보를 붙이지 않았다. 즉 백엔드 URL만 알면 로그인 없이 모든 데이터에 접근 가능했다. "폐쇄형 웹 앱"이라는 목표와 어긋나 Phase 5에서 실제 세션 인증을 도입했다.

- **세션 토큰:** `POST /auth/google`이 이메일 검증 성공 시 `app/auth/session.py`의 `create_session_token(email)`로 HS256 JWT(`{sub, iat, exp}`, `SESSION_SECRET`로 서명, `SESSION_TTL_HOURS`만큼 유효)를 응답에 포함해 발급. 프론트는 이 토큰을 localStorage에 저장(`lib/api.ts`의 `setSessionToken`)하고 이후 모든 요청에 `Authorization: Bearer <token>`으로 첨부. 새로고침 시 `GET /auth/me`로 유효성 재확인 후 자동 로그인 복원.
- **검증:** `app/auth/session.py`의 `require_ceo` 의존성(FastAPI `Depends`)이 서명/만료 검증 후 `sub` 이메일이 여전히 화이트리스트에 있는지 재확인(화이트리스트가 나중에 바뀌어도 기존 토큰이 무력화되도록). `app/main.py`에서 `health`/`auth`/`telegram`을 제외한 모든 라우터(`tasks`/`schedules`/`directives`/`finance`/`marketing`/`documents`/`office`/`agents`/`audit`)에 `dependencies=[Depends(require_ceo)]`로 일괄 적용.
- **WebSocket 인증:** 브라우저 `WebSocket` API는 커스텀 헤더를 못 보내므로 `/agents/ws`는 `?token=` 쿼리파라미터로 세션 토큰을 받아 연결 수락(`accept()`) 전에 직접 검증하고, 실패 시 핸드셰이크 자체를 거부한다(라우터 레벨 `dependencies=`는 REST용 `agent_status`에만 적용).
- **텔레그램 웹훅 보호:** `/telegram/webhook`은 CEO 세션이 아니라 텔레그램이 직접 호출하므로 별도 방식으로 보호한다 — 실배포 시 `setWebhook(secret_token=...)`으로 등록하면 텔레그램이 매 요청에 `X-Telegram-Bot-Api-Secret-Token` 헤더를 실어보내고, `TELEGRAM_WEBHOOK_SECRET`가 설정돼 있으면 이를 검증(값이 비어있으면 로컬 개발 편의를 위해 검사를 건너뜀 — webhook을 아직 등록하지 않은 상태라 실질적 위험 없음).
- **감사로그:** `GET /audit/log`(`app/api/audit.py`)가 `agent_runs`(에이전트 실행 이력)와 `approvals`(CEO 승인/반려/보완 결정)를 시간순으로 합쳐 반환. Dashboard View에 표로 노출.
