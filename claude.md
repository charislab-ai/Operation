# CharisLab AI OS Development Guidelines (claude.md) - v4.0

이 문서는 Claude Code가 CharisLab AI OS 프로젝트를 완벽하게 구현하기 위한 전역 시스템 프롬프트입니다. 메타버스 UI뿐만 아니라 데이터 시각화(대시보드/달력)와 소셜 미디어 마케팅 자동화 기능이 필수적으로 포함되어야 합니다.

## 1. Project Core Information
- **프로젝트명:** CharisLab AI OS
- **운영 환경:** `charislab.kr/operation` 하위 폐쇄형 웹 앱 + 모바일 웹 지원
- **UI/UX 3대 뷰(View):** 
  1. Metaverse View (Phaser.js 2.5D 아바타)
  2. Calendar View (프로젝트/일정 관리)
  3. Dashboard View (차트/그래프 기반 데이터 시각화)
- **디자인 테마:** 보라색(#886AFF, #5771f8) 브랜드 컬러 기반.

## 2. Hierarchical Multi-Agent Architecture (LangGraph)
1.  **CEO (User Input):** 지시사항 및 에셋(영수증 등) 입력.
2.  **Executive Board (Supervisor Node):** CFO, CTO, CMO, CPO 에이전트 간의 회의 및 Task 라우팅.
3.  **Worker Nodes (실무 수행):**
    -   **PM Agent:** 전체 프로젝트를 하위 Task로 분할하고 DB의 `schedules` 테이블에 기간과 담당자를 지정하여 등록 (Calendar View 연동).
    -   **Marketing Agent (CMO):** 
        - SPING, SnapTale, SyncDay 등 각 프로덕트 특성에 맞춰 홍보용 카드뉴스 및 이미지/텍스트 생성.
        - **API Integration:** Instagram Graph API, Facebook Marketing API, TikTok API를 직접 호출하여 콘텐츠 포스팅 및 광고 스케줄링.
        - **Tracking:** 포스팅된 콘텐츠의 조회수, 클릭률, 전환율을 주기적으로 수집하여 DB `marketing_metrics` 테이블에 저장 (Dashboard 연동).
    -   **Finance Agent (CFO):** 영수증 OCR -> 복식부기 DB 저장 -> 부가세/종소세 관리.
    -   **Dev/RAG Agent:** 코드 작성(로컬 파일 시스템 제어), 전사 문서 벡터화 검색.

## 3. Technology Stack & Key Implementations
- **프론트엔드 시각화:** React, Vite, TailwindCSS. 
  - 달력 구현을 위해 `FullCalendar` 또는 `react-big-calendar` 사용.
  - 그래프/차트 렌더링을 위해 `Recharts` 또는 `Chart.js` 사용.
- **마케팅 자동화 연동:** Python 백엔드(FastAPI)에 SNS 채널 포스팅을 위한 OAuth 인증 및 Webhook 수신 로직 추가.
- **데이터베이스 (Supabase):** 
  - `tasks`: 상태(To-Do, In Progress, Done), 시작/종료일, 담당 에이전트.
  - `marketing_metrics`: 일자별 채널별 성과 지표 로깅.
- **Human-in-the-Loop:** 텔레그램 승인/반려/보완 체계 유지. 콘텐츠 포스팅 전 최종 시안은 반드시 텔레그램 결재를 거치도록 설정.

## 4. Development Instructions for Claude Code
1.  **Dashboard & Calendar UI:** 프론트엔드 작업 시 메타버스 뷰와 함께 일정/지표를 한눈에 볼 수 있는 UI 레이아웃(사이드바를 통한 View 전환)을 설계하라.
2.  **Marketing Automation Tool:** Marketing Agent가 이미지 생성(DALL-E) 후 SNS API를 통해 직접 업로드할 수 있도록 `PostToInstagram`, `PostToTikTok` 도구(Tool)를 구현하라.
3.  **State Management:** LangGraph의 State 객체에 마케팅 지표 분석 결과와 전체 스케줄 진행률 데이터를 포함하여, C-Level 회의 시 해당 데이터를 근거로 판단하도록 프롬프트를 구성하라.
