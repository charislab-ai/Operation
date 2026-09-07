# CharisLab AI OS — Frontend (Phase 4)

## 실행

```bash
npm install
cp .env.example .env   # 값 채워넣기 (docs/SETUP.md 참고)
npm run dev
```

## 현재 포함된 것

**Phase 0**
- Google 로그인 (백엔드 `/auth/google`로 검증)
- 사이드바로 Metaverse / Calendar / Dashboard 3개 뷰 전환

**Phase 1**
- 상단 지시 입력바(`DirectiveBar`) — CEO 지시 입력 → `/directives` 호출 → 승인 상태 폴링
- Calendar View — FullCalendar로 `/schedules?with_task=true` 연동, Task 상태별 색상 표시

**Phase 2**
- Dashboard View — Recharts로 도넛 차트(업무 상태별 분포)와 막대 그래프(월별 확정 지출) 렌더링
- 영수증 업로드 폼 — `/finance/receipts`로 이미지 전송, 텔레그램 승인 요청까지 트리거

**Phase 3**
- Dashboard View에 선 그래프 추가 — `/marketing/metrics`를 채널별(Instagram/Facebook/TikTok/Threads) 라인으로 표시

**Phase 4**
- Metaverse View — Phaser.js로 대표실/개발실/마케팅실/경영지원실 4개 룸 렌더링(`OfficeScene.ts`). 빈 그리드 칸 클릭 시 에이전트 책상 추가, 책상 클릭 시 최근 실행 로그 팝업+삭제. `/agents/status`를 5초 간격 폴링해 활성 에이전트를 초록 강조 표시
- RAG 문서 업로드/검색 API 클라이언트 함수(`createDocument`, `searchDocuments`) 추가(아직 전용 UI는 없음)

나머지 로드맵은 `../docs/PHASE_PLAN.md` 참고.
