"""정기 자동 마케팅 발행 - CEO가 매번 지시하지 않아도 주기적으로 콘텐츠를 만들어 결재에 올린다.

동작: 앱 서버가 살아있는 동안 주기적으로 설정(marketing_auto_schedule 단일 행)을 확인해서,
마지막 실행으로부터 interval_hours가 지났으면 등록된 앱을 번갈아가며 마케팅 지시를 자동 생성한다.
생성된 지시는 평소와 똑같이 승인 대기로 올라가므로, CEO 결재 없이 게시되는 일은 없다.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.db.supabase_client import get_supabase
from app.services.directive_intake import create_directive_and_run

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 30 * 60  # 30분마다 "지금 돌릴 때가 됐는지"만 확인(실제 생성은 주기마다 1회)

DIRECTIVE_TEMPLATE = (
    "{product} 앱의 SNS 홍보 콘텐츠를 만들어줘. 정기 발행이니 지난 번과는 다른 소재/형식으로, "
    "최근 마케팅 벤치마킹 인사이트를 반영해서 새롭게 구성해줘."
)


def _load_settings() -> dict | None:
    rows = get_supabase().table("marketing_auto_schedule").select("*").eq("id", 1).execute().data
    return rows[0] if rows else None


def _pick_next_product(settings_row: dict) -> str | None:
    """설정에 목록이 있으면 그걸, 없으면 등록된 앱 전체를 순서대로 돌아가며 고른다."""
    products = settings_row.get("products") or [
        r["name"] for r in get_supabase().table("products").select("name").order("name").execute().data
    ]
    if not products:
        return None
    last = settings_row.get("last_product")
    if last in products:
        return products[(products.index(last) + 1) % len(products)]
    return products[0]


def _is_due(settings_row: dict) -> bool:
    if not settings_row.get("enabled"):
        return False
    last_run = settings_row.get("last_run_at")
    if not last_run:
        return True
    try:
        last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - last_dt >= timedelta(hours=settings_row.get("interval_hours") or 72)


async def run_auto_marketing_once(graph) -> str | None:
    """지금이 발행할 때면 지시를 하나 만들고 그 thread_id를 반환한다. 아니면 None."""
    settings_row = _load_settings()
    if not settings_row or not _is_due(settings_row):
        return None

    product = _pick_next_product(settings_row)
    if not product:
        logger.warning("자동 마케팅: 등록된 앱이 없어 건너뜀")
        return None

    # 먼저 실행 시각을 찍어둬야 처리가 오래 걸려도 중복 생성되지 않는다.
    get_supabase().table("marketing_auto_schedule").update(
        {"last_run_at": datetime.now(timezone.utc).isoformat(), "last_product": product}
    ).eq("id", 1).execute()

    result = await create_directive_and_run(graph, DIRECTIVE_TEMPLATE.format(product=product), [])
    logger.info("자동 마케팅 지시 생성: %s (%s)", result.get("thread_id"), product)
    return result.get("thread_id")


async def run_auto_marketing_loop(graph) -> None:
    """앱이 떠 있는 동안 계속 도는 백그라운드 루프. 실패해도 다음 주기에 다시 시도한다."""
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            await run_auto_marketing_once(graph)
        except Exception:
            logger.exception("자동 마케팅 발행 실패 - 다음 주기에 재시도")
