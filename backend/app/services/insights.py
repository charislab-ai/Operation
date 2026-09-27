"""게시 성과 실측 수집 - 인스타그램 Insights API로 조회·도달·저장·공유를 받아 저장한다.

Why: 지금까지는 "어디에 올렸는지"(permalink)만 남기고 성과는 비워뒀다. 지어낸 숫자로 판단하는
사고를 막기 위한 의도적 선택이었지만(0019 마이그레이션), 그 결과 **무엇이 먹히는지 알 수 없는
상태**가 됐다 - 좋아요 수만 보이고 몇 명에게 닿았는지도 몰랐다. instagram_manage_insights
권한이 붙어 실제 지표를 받을 수 있게 되어 여기서 수집한다.

여전히 원칙은 같다: **받아온 값만 저장하고 없는 값은 비워둔다**(추정하지 않음).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from app.config import settings
from app.db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"
_COLLECT_INTERVAL_SECONDS = 6 * 60 * 60
_LOOKBACK_DAYS = 60  # 오래된 게시물은 수치가 거의 고정되므로 최근 것만 갱신한다

# 미디어 종류별로 지원하는 지표가 다르다(실측: 릴스는 profile_visits/follows 미지원 → 400).
_COMMON = ["views", "reach", "saved", "shares", "likes", "comments", "total_interactions"]
_METRICS_BY_TYPE = {
    "VIDEO": _COMMON,                              # 릴스
    "REELS": _COMMON,
    "IMAGE": _COMMON + ["profile_visits", "follows"],
    "CAROUSEL_ALBUM": _COMMON + ["profile_visits", "follows"],
}


async def _media_type(client: httpx.AsyncClient, media_id: str, token: str) -> str | None:
    r = await client.get(f"{GRAPH}/{media_id}", params={"fields": "media_type", "access_token": token})
    return r.json().get("media_type") if r.status_code == 200 else None


async def fetch_media_insights(client: httpx.AsyncClient, media_id: str, token: str) -> dict:
    """게시물 하나의 지표를 가져온다. 지원하지 않는 지표가 섞이면 전체가 400이 나므로
    미디어 종류에 맞는 목록만 요청한다."""
    mtype = await _media_type(client, media_id, token)
    metrics = _METRICS_BY_TYPE.get(mtype or "", _COMMON)
    r = await client.get(
        f"{GRAPH}/{media_id}/insights", params={"metric": ",".join(metrics), "access_token": token}
    )
    data = r.json()
    if "data" not in data:
        logger.warning("인사이트 조회 실패 %s: %s", media_id, str(data)[:200])
        return {"media_type": mtype}
    values = {d["name"]: d["values"][0]["value"] for d in data["data"]}
    values["media_type"] = mtype
    return values


async def collect_post_insights() -> int:
    """최근 게시물들의 성과를 갱신한다. 갱신한 건수를 반환."""
    token = settings.meta_page_access_token
    if not token:
        return 0
    supabase = get_supabase()
    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
    rows = (
        supabase.table("marketing_metrics")
        .select("id, post_id, channel, metric_date")
        .gte("metric_date", since)
        .execute()
        .data
    )
    targets = [r for r in rows if r.get("post_id") and r.get("channel") == "instagram"]
    if not targets:
        return 0

    updated = 0
    async with httpx.AsyncClient(timeout=30) as client:
        for row in targets:
            try:
                values = await fetch_media_insights(client, row["post_id"], token)
            except Exception:
                logger.exception("인사이트 수집 실패: %s", row["post_id"])
                continue
            patch = {
                key: values.get(key)
                for key in ("views", "reach", "saved", "shares", "likes", "comments", "profile_visits", "follows")
                if values.get(key) is not None
            }
            if not patch:
                continue
            patch["media_type"] = values.get("media_type")
            patch["collected_at"] = datetime.now(timezone.utc).isoformat()
            # impressions 컬럼은 예전 스키마 잔재 - 지금은 views가 같은 의미라 함께 채워
            # 기존 화면(대시보드 차트)이 깨지지 않게 한다.
            if values.get("views") is not None:
                patch["impressions"] = values["views"]
            supabase.table("marketing_metrics").update(patch).eq("id", row["id"]).execute()
            updated += 1
    return updated


async def snapshot_account() -> dict | None:
    """계정 전체 추이(팔로워/도달)를 하루 한 번 남긴다 - 게시물 지표만으로는 계정이 자라는지 알 수 없다."""
    token, ig = settings.meta_page_access_token, settings.meta_instagram_business_account_id
    if not (token and ig):
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        acc = await client.get(
            f"{GRAPH}/{ig}", params={"fields": "followers_count,media_count", "access_token": token}
        )
        info = acc.json() if acc.status_code == 200 else {}
        reach = views = None
        try:
            r = await client.get(
                f"{GRAPH}/{ig}/insights",
                params={"metric": "reach,profile_views", "period": "day", "metric_type": "total_value", "access_token": token},
            )
            for d in r.json().get("data", []):
                value = d.get("total_value", {}).get("value")
                if d["name"] == "reach":
                    reach = value
                elif d["name"] == "profile_views":
                    views = value
        except Exception:
            logger.exception("계정 인사이트 조회 실패")

    snapshot = {
        "channel": "instagram",
        "snapshot_date": date.today().isoformat(),
        "followers": info.get("followers_count"),
        "media_count": info.get("media_count"),
        "reach": reach,
        "profile_views": views,
    }
    get_supabase().table("account_snapshots").upsert(
        snapshot, on_conflict="channel,snapshot_date"
    ).execute()
    return snapshot


async def run_insights_loop() -> None:
    """앱 기동 중 주기적으로 성과를 수집한다(app/main.py lifespan에서 실행)."""
    while True:
        try:
            count = await collect_post_insights()
            await snapshot_account()
            if count:
                logger.info("게시 성과 %d건 갱신", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("성과 수집 루프 오류 - 다음 주기에 재시도")
        await asyncio.sleep(_COLLECT_INTERVAL_SECONDS)
