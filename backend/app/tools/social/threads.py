from app.tools.social.base import PostContent, PostResult


class ThreadsSocialPoster:
    """Threads 실연동 어댑터 — 별도 권한(threads_business_content_publish) 심사 완료 후 구현 (Phase 5)."""

    def __init__(self, product: str) -> None:
        self.product = product

    async def post(self, content: PostContent) -> PostResult:
        raise NotImplementedError("Threads 실연동은 Phase 5에서 구현 (EXTERNAL_APIS.md 참고)")
