"""입사 추천 - 입사 예정(onboarding) 직원의 입사 조건을 시스템이 감시하다가 채워지면 CEO에게 알린다.

Why: 퍼포먼스 마케터처럼 "데이터가 쌓인 뒤에 투입해야 의미 있는" 자리가 있는데, 얼마나 쌓여야
하는지를 CEO가 계속 신경 써야 하면 결국 영영 입사를 못 시킨다(CEO 지적). 조건을 코드에 명시해
두고, 진행률을 직원 화면에 항상 보여주고, 다 채워지면 텔레그램으로 먼저 "이제 입사시킬 때입니다"
라고 알린다. 알림의 버튼으로 바로 입사시킬 수 있고, 조건 충족 전이라도 CEO가 원하면 언제든
직접 입사시킬 수 있다(조건은 추천일 뿐 강제가 아니다).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_WATCH_INTERVAL_SECONDS = 6 * 60 * 60  # 6시간마다 확인(DB 조회뿐이라 비용 없음)

# 퍼포먼스 마케터 입사 조건 - "성과로 판단한다"는 그 자리의 존재 이유가 성립하려면
# ①판단할 게시물이 여러 건 있고 ②비교할 제품이 둘 이상이며 ③추세를 볼 만한 기간이 지나야 한다.
_MIN_POSTS = 6
_MIN_PRODUCTS = 2
_MIN_DAYS = 14


def _check(label: str, current: int, needed: int, unit: str) -> dict:
    return {
        "label": label,
        "current": min(current, needed),
        "raw": current,
        "needed": needed,
        "unit": unit,
        "met": current >= needed,
    }


def _performance_marketer_readiness() -> dict:
    """실제 게시 기록(marketing_metrics)을 근거로 입사 조건 충족도를 계산한다."""
    rows = (
        get_supabase()
        .table("marketing_metrics")
        .select("product, metric_date, post_id, permalink")
        .order("metric_date")
        .execute()
        .data
    )
    # 실제로 게시된 것만 센다(게시 시 publish_worker가 post_id/permalink와 함께 기록).
    posted = [r for r in rows if r.get("post_id") or r.get("permalink")]
    products = {r["product"] for r in posted if r.get("product")}

    days = 0
    if posted:
        first = min(r["metric_date"] for r in posted if r.get("metric_date"))
        try:
            days = (datetime.now(timezone.utc).date() - datetime.fromisoformat(first).date()).days
        except (TypeError, ValueError):
            days = 0

    checks = [
        _check("실제 게시 건수", len(posted), _MIN_POSTS, "건"),
        _check("게시한 제품 수", len(products), _MIN_PRODUCTS, "개"),
        _check("첫 게시 이후 경과", days, _MIN_DAYS, "일"),
    ]
    return {
        "checks": checks,
        "ready": all(c["met"] for c in checks),
        "why": "성과로 판단하는 자리라, 판단할 게시물(여러 건)과 비교할 제품(둘 이상), "
        "추세를 볼 기간(2주)이 갖춰져야 제 역할을 합니다.",
    }


# agent_key -> 입사 조건 계산 함수. 입사 예정으로 새 직원을 채용하면 여기에 조건을 추가한다.
READINESS_RULES = {"performance_marketer": _performance_marketer_readiness}


def readiness_of(agent_key: str) -> dict | None:
    rule = READINESS_RULES.get(agent_key)
    if not rule:
        return None
    try:
        result = rule()
    except Exception:
        logger.exception("입사 조건 계산 실패: %s", agent_key)
        return None
    done = sum(1 for c in result["checks"] if c["met"])
    result["progress"] = round(done / len(result["checks"]) * 100) if result["checks"] else 0
    return result


async def check_and_notify() -> int:
    """입사 조건을 다 채운 입사 예정 직원을 CEO에게 추천한다(직원당 1회). 보낸 건수를 반환."""
    from app.tools.telegram_bot import send_hire_recommendation

    supabase = get_supabase()
    candidates = (
        supabase.table("employees").select("*").eq("status", "onboarding").execute().data
    )
    sent = 0
    for employee in candidates:
        if employee.get("hire_recommended_at"):
            continue  # 이미 추천함 - 같은 알림을 반복하지 않는다
        readiness = readiness_of(employee["agent_key"])
        if not readiness or not readiness["ready"]:
            continue
        try:
            await send_hire_recommendation(employee, readiness)
        except Exception:
            logger.exception("입사 추천 알림 전송 실패: %s", employee["agent_key"])
            continue
        supabase.table("employees").update(
            {"hire_recommended_at": datetime.now(timezone.utc).isoformat()}
        ).eq("agent_key", employee["agent_key"]).execute()
        sent += 1
    return sent


def hire(agent_key: str) -> dict | None:
    """입사 처리(status를 active로). 텔레그램 버튼과 직원 화면이 같은 경로를 쓴다."""
    from app.graphs.workers._marketing_shared import fetch_employees

    result = (
        get_supabase()
        .table("employees")
        .update({"status": "active", "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("agent_key", agent_key)
        .execute()
    )
    fetch_employees(force=True)  # 이름/상태 캐시 갱신 - 다음 지시부터 바로 반영
    return result.data[0] if result.data else None


async def run_hiring_watch_loop() -> None:
    """앱 기동 중 주기적으로 입사 조건을 확인한다(app/main.py lifespan에서 실행)."""
    while True:
        try:
            count = await check_and_notify()
            if count:
                logger.info("입사 추천 알림 %d건 전송", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("입사 조건 확인 루프 오류 - 다음 주기에 재시도")
        await asyncio.sleep(_WATCH_INTERVAL_SECONDS)
