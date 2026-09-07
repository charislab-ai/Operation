from app.tools.social.base import PostContent, PostResult


class TikTokSocialPoster:
    """TikTok 실연동 어댑터 — Content Posting API Production 심사 완료 후 구현 (Phase 5).

    PRD.md §5.1에 따라 전 제품 통합 계정("CharisLab")을 고정 사용하므로, Meta와 달리
    product별 계정 선택 로직이 필요 없다.
    """

    async def post(self, content: PostContent) -> PostResult:
        raise NotImplementedError("TikTok 실연동은 Phase 5에서 구현 (EXTERNAL_APIS.md 참고)")
