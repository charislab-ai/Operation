"""카드 한 장을 다시 그리는 공용 헬퍼 - AI 호출 없이 보관된 원본 사진 위에 문구만 다시 얹는다.

슬라이드 편집기(app/api/marketing.py)와 브랜드 QA 자동 교정(app/graphs/workers/brand_qa.py)이
같은 로직을 쓴다 - 둘 다 "사진은 그대로 두고 문구/틀만 바꿔 다시 그리는" 작업이라 비용이 0이다.
"""

import httpx

from app.tools.ai.image.card_renderer import DEFAULT_BRAND, render_comic_panel
from app.tools.ai.image.layout_engine import render_composed


async def fetch_image_bytes(url: str | None) -> bytes:
    """원본 사진을 공개 URL에서 내려받는다. 실패하면 빈 bytes - layout_engine이 사진 없는
    레이아웃과 같은 경로로 처리하므로 호출부가 죽지는 않는다."""
    if not url:
        return b""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url)
        except Exception:
            return b""
    return resp.content if resp.status_code == 200 else b""


def brand_color_of(product: str) -> tuple[int, int, int]:
    from app.graphs.workers._marketing_shared import canonical_product, fetch_products, hex_to_rgb

    row = fetch_products().get(canonical_product(product)) or {}
    return hex_to_rgb(row.get("brand_color")) or DEFAULT_BRAND


def render_slide(
    slide: dict,
    product: str,
    page_label: str | None,
    brand: tuple[int, int, int],
    fmt: str,
    photo: bytes,
) -> bytes:
    if fmt == "instatoon":
        # 인스타툰은 AI가 그린 컷 그림 위에 말풍선/자막만 다시 얹는다(레이아웃 spec 미사용).
        return render_comic_panel(
            photo, slide.get("headline", ""), slide.get("subtext", ""), product, page_label, brand
        )
    return render_composed(
        photo,
        slide.get("headline", ""),
        slide.get("subtext", ""),
        product,
        page_label,
        brand,
        spec=slide.get("layout_spec") or {},
    )
