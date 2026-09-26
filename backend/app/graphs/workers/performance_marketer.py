"""퍼포먼스 마케터 - 지난 성과를 근거로 "이번엔 무엇을 누구에게" 정한다.

**입사 예정(onboarding) 상태로 채용된 자리다.** employees 테이블의 status가 'active'가 되기
전까지 이 노드는 LLM을 호출하지 않고 그대로 통과한다 - CEO가 직원 명단 화면에서 "입사시키기"를
눌러야 실제로 일을 시작한다.

Why 지금 당장 투입하지 않는가: 판단 근거가 될 실제 게시 성과 데이터(게시 이력, permalink 지표)가
아직 거의 없다. 데이터 없이 성과 기반 기획자를 앞단에 두면 "그럴듯한 말을 지어내는 단계"가 하나
늘어날 뿐이고, 그 판단이 마케팅 디렉터의 브리핑을 오히려 좁힌다. 게시가 쌓인 뒤 입사시키는 게 맞다.
"""

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import CampaignPlan
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import addressing_note, employee_of, original_ceo_text
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 퍼포먼스 마케터입니다. 이번 게시물을 "무엇을·누구에게·
어느 채널에·어떤 각도로" 낼지 정합니다. 콘텐츠를 직접 만들지는 않습니다 - 마케팅 디렉터가
당신의 결정을 받아 구성을 설계합니다.

판단 규칙:
- **감이 아니라 아래 데이터로 결정하세요.** 지난 게시 이력(제품/채널/시점)과 성과 지표가
  주어집니다. 오래 안 나간 제품, 성과가 좋았던 채널/각도를 우선하세요
- 데이터가 부족하면 그 사실을 rationale에 솔직히 적고, 게시 간격만으로 보수적으로 고르세요
  (없는 성과를 지어내지 마세요)
- hook_angle은 지난 회차와 겹치지 않게 하세요 - 같은 각도의 반복이 성과를 떨어뜨립니다
- CEO 지시문에 제품/채널이 명시돼 있으면 그게 최우선입니다"""


async def performance_marketer_node(state: OSState, config: RunnableConfig) -> dict:
    """입사 전이면 아무것도 하지 않고 통과한다(LLM 호출 없음 = 비용 0)."""
    me = employee_of("performance_marketer")
    if me.get("status") != "active":
        return {}

    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("PerformanceMarketer", {"ceo_directive": state.get("ceo_directive")}, thread_id=thread_id)
    supabase = get_supabase()

    history = (
        supabase.table("marketing_posts")
        .select("product, channel, posted_at, permalink")
        .order("posted_at", desc=True)
        .limit(15)
        .execute()
        .data
        if _has_table(supabase, "marketing_posts")
        else []
    )
    metrics = (
        supabase.table("marketing_metrics")
        .select("product, channel, metric_date, impressions, clicks, conversions")
        .order("metric_date", desc=True)
        .limit(30)
        .execute()
        .data
    )
    products = supabase.table("products").select("name, description, target_audience").execute().data

    data_context = (
        "[등록된 제품]\n" + "\n".join(f"- {p['name']}: {p.get('description') or ''}" for p in products)
        + "\n\n[최근 게시 이력]\n" + ("\n".join(f"- {h}" for h in history) if history else "(없음)")
        + "\n\n[수집된 성과 지표]\n" + ("\n".join(f"- {m}" for m in metrics) if metrics else "(아직 없음)")
    )

    plan = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=f"[CEO 지시문]\n{original_ceo_text(state)}"
                f"{addressing_note(state, 'performance_marketer')}\n\n{data_context}",
            ),
        ],
        CampaignPlan,
        thread_id=thread_id,
        agent_name="PerformanceMarketer",
    )

    result = plan.model_dump()
    finish_run(run_id, result)
    return {
        "campaign_plan": result,
        "messages": [
            {
                "role": "assistant",
                "content": f"[PerformanceMarketer] {plan.product}/{plan.channel} - {plan.objective} ({plan.rationale})",
            }
        ],
    }


def _has_table(supabase, name: str) -> bool:
    """게시 이력 테이블은 아직 없을 수 있다 - 없으면 조용히 빈 이력으로 진행한다."""
    try:
        supabase.table(name).select("*").limit(1).execute()
        return True
    except Exception:
        return False
