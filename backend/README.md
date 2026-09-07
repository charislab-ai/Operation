# CharisLab AI OS — Backend (Phase 4)

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 값 채워넣기 (docs/SETUP.md 참고)
uvicorn app.main:app --reload --port 8000
```

앱 시작 시 `SUPABASE_DB_URL`로 LangGraph checkpointer(Postgres)를 초기화한다 — 값이 비어있으면 시작에 실패한다(`docs/SETUP.md` 1.5 참고).

## 현재 포함된 것

**Phase 0**
- `/health` — 헬스체크
- `/auth/google` — Google ID token 검증 + 이메일 화이트리스트 체크

**Phase 1**
- `POST /directives` — CEO 지시 입력 → LangGraph 실행(Supervisor 3-way 라우팅: BizDev/PM/Marketing) → 텔레그램 승인 요청
- `GET /directives/{thread_id}` — 진행 상태 조회
- `GET/POST/PATCH/DELETE /tasks`, `GET/POST /schedules` — Task/Schedule CRUD
- `app/tools/ai/llm/` — Claude CLI(1순위)/API(2순위 폴백) 추론 provider (ARCHITECTURE.md §7.1)

**Phase 2**
- `POST /finance/receipts` — 영수증 업로드(멀티파트) → Supabase Storage 저장 → Gemini Vision OCR → 계정 매핑 → 텔레그램 승인 요청
- `GET /finance/entries`, `GET /finance/summary` — 원장 조회 / 대시보드용 월별 집계(확정된 분개만)
- `app/tools/ai/vision/` — Gemini Vision 기반 `VisionOCRProvider` (실 사용에는 `GOOGLE_GEMINI_API_KEY` 필요)
- `app/workers/finance_worker.py` — OCR 결과 → 복식부기 계정 매핑(순수 함수, LangGraph 노드 아님)

**Phase 3**
- `app/graphs/workers/marketing_worker.py` — CEO 지시 → product/channel/caption/image_prompt 추출 → 이미지 생성(`IMAGE_PROVIDER=mock` 기본값)
- `app/graphs/workers/publish_worker.py` — 승인된 콘텐츠를 `app/tools/social/`(Mock 기본)로 게시 → `marketing_metrics` 기록
- `GET /marketing/metrics` — Dashboard 선그래프용
- `/telegram/webhook` — `task_plan`/`finance_entry`/`marketing_post` 3종 공용 승인 콜백 처리(`callback_data="{target_type}:{id}:{decision}"`)
- Canva/Figma MCP 기반 DesignWorker는 이번 Phase에서 제외(ARCHITECTURE.md §6 참고, 독립 백엔드에서 Claude Code 세션 전용 MCP 커넥터를 직접 호출하기 어려움)

**Phase 4**
- `POST /documents`, `GET /documents/search` — RAG 문서 업로드(청킹+OpenAI 임베딩) / pgvector 유사도 검색 (실제 키로 검증 완료)
- `app/graphs/workers/dev_worker.py` — RAG 검색 결과를 컨텍스트로 코드 변경 제안(`DevProposal`) 생성. **실제 git 저장소에 파일을 쓰거나 PR을 만들지 않음** — 텍스트 제안만 생성(위험도 관리를 위한 의도적 범위 축소)
- `app/db/agent_runs.py` — 모든 Worker 노드의 시작/종료를 `agent_runs`에 기록(최초 실사용)
- `GET /agents/status` — 최근 5분 내 미완료 실행이 있으면 active, 아니면 idle
- `GET/POST/DELETE /office/desks` — Metaverse 사무실 책상 배치 CRUD
- `/telegram/webhook`이 `task_plan`/`finance_entry`/`marketing_post`/`dev_proposal` 4종 공용으로 확장됨

RAG 자동 문서 수집(Google Drive/Notion MCP), Design Worker, 실제 저장소 쓰기 권한을 가진 Dev Agent 등은 이후 Phase에서 추가된다. 자세한 로드맵은 `../docs/PHASE_PLAN.md` 참고.
