from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
    allow_origins=["http://localhost:5173", "https://charislab.kr"],
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
app.include_router(documents.router, dependencies=protected)
app.include_router(office.router, dependencies=protected)
# agents.router는 REST(/status)와 WebSocket(/ws)이 섞여있어 라우터 전체에 일괄 dependencies를
# 걸지 않고 각 엔드포인트에서 개별적으로 인증한다(app/api/agents.py 참고) - WS는 브라우저가
# 커스텀 헤더를 못 보내 쿼리파라미터 토큰을 쓰는데, 라우터 레벨 Depends와 섞으면 동작이 불확실함
app.include_router(agents.router)
app.include_router(audit.router, dependencies=protected)
