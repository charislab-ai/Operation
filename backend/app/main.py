import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import (
    agents,
    audit,
    auth,
    directives,
    documents,
    finance,
    health,
    marketing,
    office,
    products,
    schedules,
    tasks,
    telegram,
)
from app.auth.session import require_ceo
from app.db.checkpointer import close_checkpointer, init_checkpointer
from app.graphs.build import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpointer = await init_checkpointer()
    app.state.graph = build_graph(checkpointer)
    yield
    await close_checkpointer()


app = FastAPI(title="CharisLab AI OS Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://charislab.kr",
        "https://operation.charislab.kr",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

protected = [Depends(require_ceo)]

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(telegram.router)  # 텔레그램이 직접 호출 - CEO 세션 대신 자체 webhook secret으로 보호
app.include_router(tasks.router, dependencies=protected)
app.include_router(schedules.router, dependencies=protected)
app.include_router(directives.router, dependencies=protected)
app.include_router(finance.router, dependencies=protected)
app.include_router(marketing.router, dependencies=protected)
app.include_router(products.router, dependencies=protected)
app.include_router(documents.router, dependencies=protected)
app.include_router(office.router, dependencies=protected)
# agents.router는 REST(/status)와 WebSocket(/ws)이 섞여있어 라우터 전체에 일괄 dependencies를
# 걸지 않고 각 엔드포인트에서 개별적으로 인증한다(app/api/agents.py 참고) - WS는 브라우저가
# 커스텀 헤더를 못 보내 쿼리파라미터 토큰을 쓰는데, 라우터 레벨 Depends와 섞으면 동작이 불확실함
app.include_router(agents.router)
app.include_router(audit.router, dependencies=protected)

# 프로덕션 배포(루트 Dockerfile) 시에만 빌드된 프론트엔드(dist)가 backend/static에 존재.
# 로컬 개발(uvicorn --reload, docker-compose)에서는 프론트를 Vite dev 서버로 따로 띄우므로
# 이 디렉터리가 없고, 그 경우 정적 서빙을 건너뛴다. API 라우터가 먼저 등록되어 있으므로
# /auth, /tasks 등 API 경로는 그대로 우선 매칭되고, 나머지 경로만 정적 파일(SPA)로 폴백된다.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
