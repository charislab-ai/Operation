from app.config import settings
from app.tools.social.base import SocialPoster
from app.tools.social.meta import MetaSocialPoster
from app.tools.social.mock import MockSocialPoster
from app.tools.social.threads import ThreadsSocialPoster
from app.tools.social.tiktok import TikTokSocialPoster


def get_social_poster(channel: str, product: str) -> SocialPoster:
    """SOCIAL_ADAPTER=mock(기본값)이면 채널과 무관하게 Mock을 반환한다 (ARCHITECTURE.md §5)."""
    if settings.social_adapter == "mock":
        return MockSocialPoster(channel)
    if channel in ("instagram", "facebook"):
        return MetaSocialPoster(channel, product)
    if channel == "tiktok":
        return TikTokSocialPoster()
    if channel == "threads":
        return ThreadsSocialPoster(product)
    raise ValueError(f"unsupported channel: {channel}")
