import uuid

from app.tools.social.base import PostContent, PostResult


class MockSocialPoster:
    """SocialPoster 구현체 — 실제 API 심사가 끝나기 전까지 쓰는 기본 어댑터 (ARCHITECTURE.md §5)."""

    def __init__(self, channel: str) -> None:
        self.channel = channel

    async def post(self, content: PostContent) -> PostResult:
        return PostResult(post_id=f"mock-{self.channel}-{uuid.uuid4()}")
