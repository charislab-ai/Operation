from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import GoalPlan
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab AI OS의 Supervisor(C-Level 라우터 겸 킥오프 담당)입니다.
CEO의 지시를 읽고 이번 지시를 처리하는 데 어떤 부서가 필요한지 판단하세요:
- "marketing": 제품 홍보 콘텐츠 제작·SNS 게시 요청 (이 시스템의 주 업무)
- "dev": 기존 앱/서비스의 코드 수정, 버그 수정, 기능 개발 요청인 경우

애매하면 marketing을 고르세요. 두 부서가 동시에 필요한 지시라면 둘 다 고르고, 각 부서가
정확히 뭘 해야 하는지 킥오프 브리핑을 하나씩 작성하세요(그 부서 담당자에게 바로 전달할
지시문처럼)."""


async def supervisor_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("Supervisor", {"ceo_directive": state["ceo_directive"]}, thread_id=thread_id)
    plan = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=state["ceo_directive"]),
        ],
        GoalPlan,
        thread_id=thread_id,
        agent_name="Supervisor",
    )

    routes = plan.routes or ["marketing"]

    finish_run(run_id, {"routes": routes, "reason": plan.reason})
    return {
        "active_departments": routes,
        "worker_briefs": plan.worker_briefs,
        "messages": [{"role": "assistant", "content": f"[Supervisor] {routes} 라우팅 — {plan.reason}"}],
    }


def route_after_supervisor(state: OSState) -> list[str]:
    routes = state.get("active_departments") or ["marketing"]
    node_by_route = {"marketing": "marketing_director_brief", "dev": "dev_worker"}
    nodes = [node_by_route[r] for r in routes if r in node_by_route]
    return nodes or ["marketing_director_brief"]
