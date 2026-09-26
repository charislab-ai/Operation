from typing import Protocol

from pydantic import BaseModel


class PostContent(BaseModel):
    caption: str
    image_urls: list[str]  # 카드뉴스는 보통 여러 장(캐러셀) - 1장이면 일반 게시물로 처리


class PostResult(BaseModel):
    post_id: str
    permalink: str | None = None  # CEO가 실제 게시물을 바로 열어볼 수 있게 - 없으면 None


class SocialPoster(Protocol):
    async def post(self, content: PostContent) -> PostResult: ...
