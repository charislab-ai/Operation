"""워커 실행 실패를 "보이게" 만드는 공통 처리.

Why: 지금까지 그래프 실행 중 예외가 나면 (1) agent_runs에 finished_at 없는 유령 행만 남고
(2) 백그라운드 태스크는 예외를 조용히 삼키고 (3) 승인은 processing 상태로 영원히 멈춰서,
CEO 화면에는 "진행중"만 며칠씩 떠 있고 원인을 알 방법이 전혀 없었다(실측: OpenAI 크레딧
소진으로 RAG 임베딩이 429를 내며 마케팅 파이프라인이 통째로 죽은 사례). 실패는 반드시
① DB에 기록되고 ② 멈춘 승인은 다시 결정 가능한 상태로 되돌려지고 ③ 텔레그램으로 알려야 한다.
"""

import logging

from app.config import settings
from app.db.agent_runs import fail_unfinished_runs
from app.db.supabase_client import get_supabase
from app.tools.telegram_bot import get_bot

logger = logging.getLogger(__name__)


def describe_error(error: BaseException) -> str:
    """CEO가 읽고 무엇을 해야 할지 알 수 있는 한국어 설명으로 바꾼다(원문도 함께 남김)."""
    raw = f"{type(error).__name__}: {error}"
    lowered = raw.lower()

    # 크레딧 소진은 공급자별 문구가 제각각이라(OpenAI: insufficient_quota / Gemini:
    # prepayment credits are depleted / Anthropic: credit balance is too low) 전부 잡아서
    # "어디에 얼마를 충전해야 하는지"까지 알려준다 - CEO가 바로 조치할 수 있어야 하므로.
    credit_markers = (
        "credit balance is too low",
        "insufficient_quota",
        "no credits remaining",
        "credit_balance_exhausted",
        "prepayment credits are depleted",
        "resource_exhausted",
    )
    if any(m in lowered for m in credit_markers):
        if "openai" in lowered or "insufficient_quota" in lowered or "credit_balance_exhausted" in lowered:
            where = "OpenAI (platform.openai.com/settings/organization/billing)"
        elif "prepayment" in lowered or "ai.studio" in lowered or "resource_exhausted" in lowered:
            where = "Google Gemini (ai.studio 프로젝트 결제)"
        elif "anthropic" in lowered:
            where = "Anthropic Claude (console.anthropic.com Plans & Billing)"
        else:
            where = "AI API"
        return f"{where} 크레딧이 소진되어 실패했습니다. 충전 후 다시 시도해주세요.\n({raw[:300]})"
    if "rate limit" in lowered or "429" in lowered:
        return f"AI API 호출 한도에 걸렸습니다. 잠시 후 재시도해주세요.\n({raw[:300]})"
    if "timeout" in lowered or isinstance(error, TimeoutError):
        return f"처리 시간이 너무 오래 걸려 중단됐습니다.\n({raw[:300]})"
    return raw[:500]


async def record_graph_failure(
    thread_id: str, error: BaseException, *, approval_id: str | None = None, notify: bool = True
) -> str:
    """그래프 실행이 실패했을 때 흔적을 남기고 CEO에게 알린다. 설명 문구를 반환한다."""
    message = describe_error(error)
    logger.exception("그래프 실행 실패 (thread_id=%s)", thread_id)
    supabase = get_supabase()

    try:
        fail_unfinished_runs(thread_id, message)
    except Exception:
        logger.exception("agent_runs 실패 마감 중 오류")

    try:
        supabase.table("directives").update({"failed_at": "now()", "last_error": message}).eq(
            "thread_id", thread_id
        ).execute()
    except Exception:
        logger.exception("directives 실패 기록 중 오류")

    # 선점(processing)해둔 승인은 다시 pending으로 되돌려야 CEO가 재시도할 수 있다 -
    # 안 되돌리면 그 카드는 영원히 결정 불가 상태로 죽는다.
    try:
        if approval_id:
            supabase.table("approvals").update({"status": "pending"}).eq("id", approval_id).eq(
                "status", "processing"
            ).execute()
        else:
            supabase.table("approvals").update({"status": "pending"}).eq("thread_id", thread_id).eq(
                "status", "processing"
            ).execute()
    except Exception:
        logger.exception("승인 상태 복구 중 오류")

    if notify and settings.telegram_ceo_chat_id:
        try:
            await get_bot().send_message(
                chat_id=settings.telegram_ceo_chat_id,
                text=f"⚠️ 업무 처리 중 오류가 발생했습니다\n\n{message}\n\n해당 업무는 다시 시도할 수 있습니다(홈페이지 업무지시 화면 참고).",
            )
        except Exception:
            logger.exception("실패 알림 전송 중 오류")

    return message
