import json

import httpx

from app.config import settings
from app.tools.social.base import PostContent, PostResult

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class MetaPostError(Exception):
    """Meta Graph API 게시 실패 — 응답 본문을 그대로 담아 상위(승인/알림 로직)에서 원인을 볼 수 있게 한다."""


class MetaSocialPoster:
    """Instagram/Facebook 실연동 어댑터 (PRD.md §5.1 — 제품별이 아닌 통합 계정 "CharisLab" 하나를 사용).

    카드뉴스는 보통 여러 장(캐러셀)이라 이미지 개수에 따라 단일/캐러셀 게시를 자동으로 나눈다.
    - Instagram 단일: 미디어 컨테이너 생성 → 퍼블리시 2단계
    - Instagram 캐러셀: 각 이미지를 is_carousel_item으로 컨테이너화 → 부모 캐러셀 컨테이너 생성 → 퍼블리시
    - Facebook 단일: /{page-id}/photos에 caption과 함께 바로 게시
    - Facebook 캐러셀: 각 이미지를 published=false로 업로드 → /{page-id}/feed에 attached_media로 묶어 게시
    """

    def __init__(self, channel: str, product: str) -> None:
        self.channel = channel
        # 통합 계정 정책이라 product는 지금 어떤 계정을 쓸지엔 영향 없음 - 캡션에 이미 제품명이
        # 들어가 있어 구분됨(MarketingWorker가 생성). 시그니처 호환을 위해 인자만 받아둔다.
        self.product = product

    async def post(self, content: PostContent) -> PostResult:
        if not settings.meta_page_access_token:
            raise MetaPostError("META_PAGE_ACCESS_TOKEN이 설정되지 않음")
        if not content.image_urls:
            raise MetaPostError("게시할 이미지가 없음")

        if self.channel == "instagram":
            return await self._post_instagram(content)
        return await self._post_facebook(content)

    async def _post_instagram(self, content: PostContent) -> PostResult:
        ig_id = settings.meta_instagram_business_account_id
        token = settings.meta_page_access_token
        async with httpx.AsyncClient(timeout=30) as client:
            if len(content.image_urls) == 1:
                create_res = await client.post(
                    f"{GRAPH_API_BASE}/{ig_id}/media",
                    data={"image_url": content.image_urls[0], "caption": content.caption, "access_token": token},
                )
                create_data = create_res.json()
                if "id" not in create_data:
                    raise MetaPostError(f"인스타그램 미디어 컨테이너 생성 실패: {create_data}")
                publish_id = create_data["id"]
            else:
                child_ids = []
                for url in content.image_urls:
                    child_res = await client.post(
                        f"{GRAPH_API_BASE}/{ig_id}/media",
                        data={"image_url": url, "is_carousel_item": "true", "access_token": token},
                    )
                    child_data = child_res.json()
                    if "id" not in child_data:
                        raise MetaPostError(f"캐러셀 항목 생성 실패: {child_data}")
                    child_ids.append(child_data["id"])

                carousel_res = await client.post(
                    f"{GRAPH_API_BASE}/{ig_id}/media",
                    data={
                        "media_type": "CAROUSEL",
                        "caption": content.caption,
                        "children": ",".join(child_ids),
                        "access_token": token,
                    },
                )
                carousel_data = carousel_res.json()
                if "id" not in carousel_data:
                    raise MetaPostError(f"캐러셀 컨테이너 생성 실패: {carousel_data}")
                publish_id = carousel_data["id"]

            publish_res = await client.post(
                f"{GRAPH_API_BASE}/{ig_id}/media_publish",
                data={"creation_id": publish_id, "access_token": token},
            )
            publish_data = publish_res.json()
            if "id" not in publish_data:
                raise MetaPostError(f"인스타그램 게시 실패: {publish_data}")

        return PostResult(post_id=publish_data["id"])

    async def _post_facebook(self, content: PostContent) -> PostResult:
        page_id = settings.meta_page_id
        token = settings.meta_page_access_token
        async with httpx.AsyncClient(timeout=30) as client:
            if len(content.image_urls) == 1:
                res = await client.post(
                    f"{GRAPH_API_BASE}/{page_id}/photos",
                    data={"url": content.image_urls[0], "caption": content.caption, "access_token": token},
                )
                data = res.json()
                if "post_id" not in data and "id" not in data:
                    raise MetaPostError(f"페이스북 게시 실패: {data}")
                return PostResult(post_id=data.get("post_id") or data["id"])

            media_fbids = []
            for url in content.image_urls:
                photo_res = await client.post(
                    f"{GRAPH_API_BASE}/{page_id}/photos",
                    data={"url": url, "published": "false", "access_token": token},
                )
                photo_data = photo_res.json()
                if "id" not in photo_data:
                    raise MetaPostError(f"페이스북 사진 업로드 실패: {photo_data}")
                media_fbids.append(photo_data["id"])

            feed_res = await client.post(
                f"{GRAPH_API_BASE}/{page_id}/feed",
                data={
                    "message": content.caption,
                    "attached_media": json.dumps([{"media_fbid": fbid} for fbid in media_fbids]),
                    "access_token": token,
                },
            )
            feed_data = feed_res.json()
            if "id" not in feed_data:
                raise MetaPostError(f"페이스북 캐러셀 게시 실패: {feed_data}")

        return PostResult(post_id=feed_data["id"])
