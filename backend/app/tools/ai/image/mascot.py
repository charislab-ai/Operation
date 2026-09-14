"""인스타툰(말풍선 만화) 형식용 - 앱별 고정 마스코트 캐릭터 참조 이미지를 만들고 재사용한다.

매 컷마다 처음부터 새로 생성하면 캐릭터 외형이 매번 바뀌어버려(AI 생성 특성) 인스타툰이라고
알아볼 수가 없다. 그래서 마스코트는 한 번만 생성해서 product-assets 버킷에 저장해두고,
이후 컷 생성 시 이 참조 이미지를 `ImageGenProvider.edit_bytes`에 넘겨 외형을 최대한 유지한다.
"""

import uuid

import httpx

from app.db.supabase_client import get_supabase
from app.tools.ai.image import get_image_gen

MASCOT_BUCKET = "product-assets"  # 이미 공개 버킷 - 새 버킷을 만들 필요 없음

_DEFAULT_PROMPT_TEMPLATE = (
    "A single cute mascot character for a mobile app called '{name}', full-body character "
    "reference sheet, centered, front-facing neutral pose, plain white background, simple flat "
    "illustration style with thick clean outlines, friendly rounded shapes, big expressive eyes, "
    "no text, no logo, no watermark, no drop shadow. Primary color should be inspired by the hex "
    "color {brand_color}. App context: {description}"
)


def _default_prompt(name: str, description: str | None, brand_color: str | None) -> str:
    return _DEFAULT_PROMPT_TEMPLATE.format(
        name=name,
        brand_color=brand_color or "#886AFF",
        description=description or "a mobile app",
    )


async def ensure_mascot(product_row: dict, *, force: bool = False) -> bytes:
    """이 제품의 마스코트 참조 이미지 바이트를 반환한다.

    product_row['mascot_asset_path']가 있고 force가 아니면 Storage에서 그대로 받아와 재사용한다
    (일관성 유지의 핵심 - 매번 같은 참조 이미지를 써야 캐릭터가 비슷하게 유지됨). 없거나
    force=True면 새로 생성해서 올리고 products.mascot_asset_path를 갱신한다(name이 실제
    products 행과 일치할 때만 - 미등록 제품이면 DB 갱신 없이 이번 한 번만 씀).
    """
    name = product_row.get("name") or "product"
    path = product_row.get("mascot_asset_path")
    bucket = get_supabase().storage.from_(MASCOT_BUCKET)

    if path and not force:
        public_url = bucket.get_public_url(path)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(public_url)
        if resp.status_code == 200:
            return resp.content
        # 버킷에서 지워졌거나 URL이 깨졌으면 아래에서 새로 생성해 복구한다.

    prompt = product_row.get("mascot_prompt") or _default_prompt(
        name, product_row.get("description"), product_row.get("brand_color")
    )
    image_bytes = await get_image_gen().generate_bytes(prompt)
    storage_path = f"mascots/{uuid.uuid4()}.png"
    bucket.upload(storage_path, image_bytes, {"content-type": "image/png"})

    if product_row.get("id"):
        get_supabase().table("products").update({"mascot_asset_path": storage_path}).eq(
            "id", product_row["id"]
        ).execute()

    return image_bytes
