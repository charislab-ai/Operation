from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import BizPlan
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 신사업개발(CSO) 에이전트입니다.
대표가 던진 아이디어를 받아 시장성·실현가능성을 검토하고, 간단한 사업 기획서로 구체화하세요."""


async def bizdev_worker_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("BizDevWorker", {"ceo_directive": state["ceo_directive"]}, thread_id=thread_id)
    plan = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=state["ceo_directive"]),
        ],
        BizPlan,
        thread_id=thread_id,
        agent_name="BizDevWorker",
    )
    brief = (
        f"[사업기획서]\n문제: {plan.problem}\n타겟 시장: {plan.target_market}\n"
        f"MVP 범위: {plan.mvp_scope}\n리스크: {plan.risks}\n다음 액션: {plan.recommended_next_action}"
    )
    finish_run(run_id, plan.model_dump())
    return {
        "biz_plan": plan.model_dump(),
        "biz_plan_brief": brief,
        "messages": [{"role": "assistant", "content": brief}],
    }
