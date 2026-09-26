"""AI 사용량 하드 리밋 - 버그로 인한 크레딧 폭주를 물리적으로 막는다.

Why: 실제로 승인 처리 중복 실행 버그로 마케팅 파이프라인이 2배로 돌아 이미지가 중복
생성된 적이 있다(실측). 그런 일이 백그라운드에서 조용히 반복되면 크레딧이 통째로 날아갈 수
있으므로, "호출하기 전에" 상한을 확인해서 넘으면 호출 자체를 막는다. 상한은 DB(ai_budget)
한 행으로 관리하고 CEO가 화면에서 조절/비상정지할 수 있다.

상한 종류:
- enabled=false: 비상 정지 - 모든 AI 호출 차단
- daily_image_limit: 하루 이미지 장수 (비용이 큰 쪽이라 가장 중요)
- daily_token_limit: 하루 LLM 토큰
- per_thread_image_limit: 업무지시 1건당 이미지 장수 (한 건이 루프 돌며 태우는 걸 방어)
"""

import logging
from datetime import datetime, timezone

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

_DEFAULTS = {
    "enabled": True,
    "daily_image_limit": 40,
    "daily_token_limit": 3_000_000,
    "per_thread_image_limit": 15,
}


class BudgetExceeded(Exception):
    """AI 사용량 상한 초과 - 호출을 막았음을 알린다(실패 기록/알림 경로를 그대로 탄다)."""


def load_budget() -> dict:
    try:
        rows = get_supabase().table("ai_budget").select("*").eq("id", 1).execute().data
        return rows[0] if rows else dict(_DEFAULTS)
    except Exception:
        logger.exception("AI 예산 설정 조회 실패 - 기본값 사용")
        return dict(_DEFAULTS)


def _limit_of(budget: dict, key: str) -> int:
    """상한값을 꺼낸다. `budget.get(key) or 기본값`으로 쓰면 상한을 0(완전 차단)으로 설정했을 때
    0이 falsy라 기본값으로 덮여버린다 - 명시적으로 None만 기본값으로 대체한다."""
    value = budget.get(key)
    return _DEFAULTS[key] if value is None else int(value)


def _today_start_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def usage_today() -> dict:
    """오늘(UTC 기준) 쓴 이미지 장수와 LLM 토큰을 센다."""
    rows = (
        get_supabase()
        .table("ai_usage_log")
        .select("kind, image_count, total_tokens")
        .gte("created_at", _today_start_iso())
        .execute()
        .data
    )
    images = sum(r.get("image_count") or 0 for r in rows if r.get("kind") == "image")
    tokens = sum(r.get("total_tokens") or 0 for r in rows if r.get("kind") == "llm")
    return {"images": images, "tokens": tokens}


def _thread_image_count(thread_id: str) -> int:
    rows = (
        get_supabase()
        .table("ai_usage_log")
        .select("image_count")
        .eq("thread_id", thread_id)
        .eq("kind", "image")
        .execute()
        .data
    )
    return sum(r.get("image_count") or 0 for r in rows)


def assert_image_budget(thread_id: str | None = None) -> None:
    """이미지 생성 직전에 호출 - 상한을 넘었으면 BudgetExceeded를 던져 호출을 막는다."""
    budget = load_budget()
    if not budget.get("enabled", True):
        raise BudgetExceeded("AI 사용이 비상 정지 상태입니다(업무지시 화면에서 해제 가능).")

    used = usage_today()
    limit = _limit_of(budget, "daily_image_limit")
    if used["images"] >= limit:
        raise BudgetExceeded(
            f"오늘 이미지 생성 상한({limit}장)에 도달해 중단했습니다. 현재 {used['images']}장 사용. "
            "상한은 업무지시 화면에서 조정할 수 있습니다."
        )

    if thread_id:
        per_thread = _limit_of(budget, "per_thread_image_limit")
        if _thread_image_count(thread_id) >= per_thread:
            raise BudgetExceeded(
                f"이 업무 지시 하나에서 이미지를 이미 {per_thread}장 생성해 중단했습니다"
                "(같은 작업이 반복 실행되는 이상 상황일 수 있어 안전장치가 작동했습니다)."
            )


def assert_llm_budget() -> None:
    """LLM 호출 직전에 호출 - 하루 토큰 상한을 넘었으면 막는다."""
    budget = load_budget()
    if not budget.get("enabled", True):
        raise BudgetExceeded("AI 사용이 비상 정지 상태입니다(업무지시 화면에서 해제 가능).")

    limit = _limit_of(budget, "daily_token_limit")
    used = usage_today()
    if used["tokens"] >= limit:
        raise BudgetExceeded(
            f"오늘 LLM 토큰 상한({limit:,})에 도달해 중단했습니다. 현재 {used['tokens']:,} 사용."
        )
