"""Supabase 무료 티어는 일정 기간(약 1주일) API 요청이 전혀 없으면 프로젝트를 자동
비활성화(pause)한다. 운영 서버(Railway)가 24시간 항상 켜져 있는 걸 이용해, 그 안에서 아주
가벼운 조회를 주기적으로 날려 활동을 유지한다 - CEO가 한동안 홈페이지를 안 켜도(예: 휴가) 그
사이에 프로젝트가 잠들어버리는 걸 막기 위함."""

import asyncio
import logging

from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

# Supabase 무료 프로젝트 비활성화 기준(약 7일)보다 훨씬 촘촘하게 - 컨테이너 재시작으로 한두 번
# 놓쳐도 여유가 크도록 12시간 간격으로 둔다.
PING_INTERVAL_SECONDS = 12 * 60 * 60


def _ping_once() -> None:
    # products 테이블에서 1행만 조회 - 실제 데이터는 필요 없고 Supabase에 요청이 갔다는 사실만
    # 중요함(비용/부하 거의 없음).
    get_supabase().table("products").select("id").limit(1).execute()


async def run_keepalive_loop() -> None:
    """앱이 켜져 있는 동안 계속 도는 백그라운드 루프. 실패해도 앱 자체는 안 죽게 예외를 삼킨다.
    기동 직후 한 번 바로 핑을 보내고(이미 비활성화 직전이었을 수 있으므로), 이후 주기적으로 반복."""
    while True:
        try:
            await asyncio.to_thread(_ping_once)
        except Exception:
            logger.exception("Supabase keepalive ping 실패 - 다음 주기에 재시도")
        await asyncio.sleep(PING_INTERVAL_SECONDS)
