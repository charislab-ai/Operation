import random
from datetime import date

from app.db.supabase_client import get_supabase
from app.graphs.state import OSState
from app.tools.social import get_social_poster
from app.tools.social.base import PostContent


async def publish_worker_node(state: OSState) -> dict:
    post = state["marketing_post"]
    poster = get_social_poster(post["channel"], post["product"])
    result = await poster.post(PostContent(caption=post["caption"], image_urls=post["image_urls"]))

    # Mock 단계: 실제 지표 수집 API 연동 전까지 그럴듯한 더미 값으로 파이프라인을 검증한다
    # (ARCHITECTURE.md §5 — 실연동 전환 시 이 부분을 실제 지표 조회로 교체).
    impressions = random.randint(200, 2000)
    clicks = int(impressions * random.uniform(0.02, 0.08))
    conversions = int(clicks * random.uniform(0.05, 0.15))

    get_supabase().table("marketing_metrics").insert(
        {
            "product": post["product"],
            "channel": post["channel"],
            "metric_date": date.today().isoformat(),
            "impressions": impressions,
            "clicks": clicks,
            "conversions": conversions,
            "post_id": result.post_id,
        }
    ).execute()

    return {
        "messages": [
            {
                "role": "assistant",
                "content": f"[Publish] {post['channel']}에 게시 완료 (post_id={result.post_id})",
            }
        ],
    }
