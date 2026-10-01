"""퍼포먼스 마케터 - 지난 성과를 근거로 "이번엔 무엇을 누구에게" 정한다.

**입사 예정(onboarding) 상태로 채용된 자리다.** employees 테이블의 status가 'active'가 되기
전까지 이 노드는 LLM을 호출하지 않고 그대로 통과한다 - CEO가 직원 명단 화면에서 "입사시키기"를
눌러야 실제로 일을 시작한다(또는 app/services/hiring.py가 성과 기준 충족 시 추천 알림을 보낸다).

에이전트로서의 구조(2단계):
1. **집계는 코드가 한다** - app/services/performance_analytics.py가 제품별/형식별 퍼짐 점수,
   게시 간격, 가장 잘 퍼진 게시물을 계산한다. 원본 행을 프롬프트에 통째로 붓던 예전 방식은
   LLM이 숫자를 잘못 더하거나 없는 추세를 지어내게 만들었다.
2. **결정은 LLM이, 검증은 다시 코드가 한다** - 내린 결정이 실제로 데이터를 따랐는지
   `_validate`가 기계적으로 따지고, 어긋나면 그 반박을 붙여 한 번 다시 결정하게 한다.
   "데이터를 보여줬으니 알아서 잘 하겠지"가 실패하는 지점을 루프로 막는다.
"""

import logging
import re

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import CampaignPlan
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import addressing_note, employee_of, original_ceo_text
from app.services import performance_analytics
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

logger = logging.getLogger(__name__)
llm = get_llm()

_MAX_ATTEMPTS = 2  # 처음 결정 + 반박 반영 재결정 1회. 더 돌려도 같은 답이 반복되는 걸 실측.

SYSTEM_PROMPT = """당신은 CharisLab의 퍼포먼스 마케터입니다. 이번 게시물을 "무엇을·누구에게·
어느 채널에·어떤 각도로" 낼지 정합니다. 콘텐츠를 직접 만들지는 않습니다 - 마케팅 디렉터가
당신의 결정을 받아 구성을 설계합니다.

판단 규칙:
- **감이 아니라 주어진 성과 데이터로 결정하세요.** 집계는 이미 끝난 상태로 주어집니다
  (제품별 퍼짐 점수, 형식별 도달, 마지막 게시 이후 경과일, 가장 잘 퍼진 게시물)
- 퍼짐 점수는 도달 대비 공유·저장·댓글의 가중 반응입니다. 조회수가 많은 게시물이 아니라
  **퍼짐 점수가 높은 게시물의 각도**가 다음에 또 통할 각도입니다
- 한 번도 안 올린 제품, 오래 비어 있는 제품을 우선하세요(노출 기회를 못 받은 제품)
- rationale에는 **근거로 삼은 수치를 그대로 인용**하세요(예: "터치러쉬 23일째 미게시",
  "릴스 평균 도달 412 vs 피드 180"). 수치 없는 rationale은 추측으로 간주합니다
- 데이터가 부족하면 그 사실을 rationale에 솔직히 적으세요(없는 성과를 지어내지 마세요)
- hook_angle은 최근 회차와 겹치지 않게 하세요 - 같은 각도의 반복이 성과를 떨어뜨립니다
- CEO 지시문에 제품/채널이 명시돼 있으면 그게 최우선입니다"""


def _recent_angles(supabase, limit: int = 5) -> list[str]:
    """최근 회차에서 쓴 후킹 각도 - 같은 각도를 또 쓰지 않게 보여준다."""
    try:
        rows = (
            supabase.table("agent_runs")
            .select("output, started_at")
            .eq("agent_name", "PerformanceMarketer")
            .not_.is_("output", "null")
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
    except Exception:
        logger.exception("과거 후킹 각도 조회 실패 - 빈 목록으로 진행")
        return []
    angles = []
    for row in rows:
        angle = (row.get("output") or {}).get("hook_angle")
        if angle:
            angles.append(angle)
    return angles


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[가-힣A-Za-z]{2,}", text or "")}


def _too_similar(angle: str, previous: list[str]) -> str | None:
    """후킹 각도가 예전 것과 사실상 같은지 - 단어 겹침으로 판정한다(의미 비교에 또 LLM을 쓰면
    비용만 늘고 판정도 흔들린다)."""
    now = _words(angle)
    if len(now) < 3:
        return None
    for old in previous:
        before = _words(old)
        if not before:
            continue
        overlap = len(now & before) / len(now)
        if overlap >= 0.6:
            return old
    return None


def _validate(plan: CampaignPlan, analysis: dict, ceo_text: str, previous: list[str]) -> list[str]:
    """내린 결정이 데이터를 실제로 따랐는지 기계적으로 따진다. 반박 목록을 돌려준다."""
    objections: list[str] = []
    gaps = analysis.get("days_since_last_post") or {}
    never = analysis.get("never_posted") or []
    # CEO가 제품을 직접 지목했으면 데이터보다 지시가 우선이므로 제품 관련 반박은 하지 않는다.
    ceo_named = any(name.lower() in ceo_text.lower() for name in list(gaps) + never)

    if not ceo_named:
        if never and plan.product not in never:
            objections.append(
                f"{', '.join(never)}은(는) 한 번도 게시하지 않았는데 {plan.product}을(를) 골랐습니다. "
                "노출 기회를 못 받은 제품을 먼저 다룰 근거가 없다면 그 제품으로 바꾸세요."
            )
        elif gaps and plan.product in gaps:
            longest = max(gaps, key=lambda k: gaps[k])
            if gaps[longest] >= gaps[plan.product] * 2 and gaps[longest] - gaps[plan.product] >= 7:
                objections.append(
                    f"{longest}은(는) {gaps[longest]}일째 안 나갔는데 {plan.product}"
                    f"({gaps[plan.product]}일 전 게시)을(를) 골랐습니다. 더 오래 비어 있는 제품을 "
                    "우선하거나, 왜 아닌지를 rationale에 수치로 적으세요."
                )

    if analysis.get("measured_posts") and not re.search(r"\d", plan.rationale):
        objections.append(
            "rationale에 수치가 하나도 없습니다. 근거로 삼은 숫자(도달/퍼짐/경과일)를 그대로 인용하세요."
        )

    repeated = _too_similar(plan.hook_angle, previous)
    if repeated:
        objections.append(f'후킹 각도가 최근 회차("{repeated}")와 거의 같습니다. 다른 각도로 바꾸세요.')

    return objections


async def performance_marketer_node(state: OSState, config: RunnableConfig) -> dict:
    """입사 전이면 아무것도 하지 않고 통과한다(LLM 호출 없음 = 비용 0)."""
    me = employee_of("performance_marketer")
    if me.get("status") != "active":
        return {}

    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("PerformanceMarketer", {"ceo_directive": state.get("ceo_directive")}, thread_id=thread_id)
    supabase = get_supabase()

    try:
        analysis = performance_analytics.analyze()
    except Exception:
        # 성과 분석이 깨져도 기획 자체는 진행되어야 한다(게시가 멈추는 게 더 큰 손해).
        logger.exception("성과 분석 실패 - 데이터 없이 진행")
        analysis = {"measured_posts": 0, "days_since_last_post": {}, "never_posted": [], "best": []}

    products = supabase.table("products").select("name, description, target_audience").execute().data
    previous = _recent_angles(supabase)
    ceo_text = original_ceo_text(state)

    data_context = (
        "[등록된 제품]\n"
        + "\n".join(f"- {p['name']}: {p.get('description') or ''}" for p in products)
        + "\n\n"
        + performance_analytics.as_brief(analysis)
        + (
            "\n\n[최근에 쓴 후킹 각도 - 겹치지 마세요]\n" + "\n".join(f"- {a}" for a in previous)
            if previous
            else ""
        )
    )

    messages = [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(
            role="user",
            content=f"[CEO 지시문]\n{ceo_text}"
            f"{addressing_note(state, 'performance_marketer')}\n\n{data_context}",
        ),
    ]

    plan: CampaignPlan | None = None
    objections: list[str] = []
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        plan = await llm.complete_structured(
            messages,
            CampaignPlan,
            thread_id=thread_id,
            agent_name="PerformanceMarketer",
        )
        objections = _validate(plan, analysis, ceo_text, previous)
        if not objections or attempt == _MAX_ATTEMPTS:
            break
        messages.append(
            Message(
                role="user",
                content="[검증 결과 - 아래를 반영해 다시 결정하세요]\n"
                + "\n".join(f"- {o}" for o in objections)
                + "\n\n반박이 타당하지 않다고 판단하면 바꾸지 말고, 그 이유를 rationale에 수치로 적으세요.",
            )
        )

    result = plan.model_dump()
    result["validation"] = {"rounds": attempt, "unresolved": objections}
    finish_run(run_id, result)

    note = f" · 검증 {attempt}회" + (f", 미해결 {len(objections)}건" if objections else "")
    return {
        "campaign_plan": result,
        "messages": [
            {
                "role": "assistant",
                "content": f"[PerformanceMarketer] {plan.product}/{plan.channel} - {plan.objective} "
                f"({plan.rationale}){note}",
            }
        ],
    }
