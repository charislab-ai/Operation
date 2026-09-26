"""인스타툰(말풍선 만화) 형식용 - 앱별 고정 마스코트 캐릭터 참조 이미지를 만들고 재사용한다.

매 컷마다 처음부터 새로 생성하면 캐릭터 외형이 매번 바뀌어버려(AI 생성 특성) 인스타툰이라고
알아볼 수가 없다. 그래서 마스코트는 한 번만 생성해서 product-assets 버킷에 저장해두고,
이후 컷 생성 시 이 참조 이미지를 `ImageGenProvider.edit_bytes`에 넘겨 외형을 최대한 유지한다.
"""

import uuid
from io import BytesIO

import httpx
from PIL import Image

from app.db.supabase_client import get_supabase
from app.tools.ai.image import get_instatoon_image_gen

MASCOT_BUCKET = "product-assets"  # 이미 공개 버킷 - 새 버킷을 만들 필요 없음

_DEFAULT_PROMPT_TEMPLATE = (
    "A single cute mascot character for a mobile app called '{name}', full-body character "
    "reference sheet, centered, front-facing neutral pose, plain white background. Korean webtoon "
    "style, simple line art, flat colors, clean bold black outlines, minimal to no gradient "
    "shading, no glossy 3D render, no photorealism - like a hand-drawn Instagram webtoon character, "
    "not a 3D app icon mascot. Friendly rounded shapes, big expressive eyes capable of showing clear "
    "emotion. No text, no logo, no watermark, no drop shadow. Primary color should be inspired by "
    "the hex color {brand_color}. App context: {description}"
)


def _looks_blank(image_bytes: bytes) -> bool:
    """거의 단색인 이미지(= 캐릭터가 없는 실패 생성물)인지 판정한다.

    Why: 터치러쉬 마스코트로 "단색 보라 사각형"이 저장돼 있던 걸 실측으로 발견했다(생성 실패
    또는 mock 이미지가 그대로 저장된 것으로 추정). 이걸 참조 이미지로 인스타툰을 그리면 캐릭터
    없는 컷이 나온다. 저장 전과 사용 전 양쪽에서 걸러 같은 사고가 반복되지 않게 한다.
    """
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB").resize((64, 64))
    except Exception:
        return True  # 열리지도 않는 이미지면 쓸 수 없다
    colors = img.getcolors(maxcolors=4096) or []
    if not colors:
        return False  # 색이 4096가지를 넘음 = 충분히 복잡한 그림
    dominant = max(count for count, _ in colors)
    return dominant / (64 * 64) > 0.92  # 한 색이 92% 이상이면 사실상 단색


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
        if resp.status_code == 200 and not _looks_blank(resp.content):
            return resp.content
        # 버킷에서 지워졌거나(404) 단색 쓰레기 이미지면 아래에서 새로 생성해 복구한다.

    prompt = product_row.get("mascot_prompt") or _default_prompt(
        name, product_row.get("description"), product_row.get("brand_color")
    )
    image_bytes = await get_instatoon_image_gen().generate_bytes(prompt)
    if _looks_blank(image_bytes):
        # 실패 생성물을 마스코트로 박아두면 이후 모든 컷이 망가진다 - 저장하지 않고 즉시 알린다.
        raise RuntimeError(
            f"{name} 마스코트 생성 결과가 비어 있습니다(단색 이미지) - 저장하지 않았습니다. "
            "이미지 생성 크레딧/설정을 확인한 뒤 앱관리에서 다시 생성해주세요."
        )
    storage_path = f"mascots/{uuid.uuid4()}.png"
    bucket.upload(storage_path, image_bytes, {"content-type": "image/png"})

    if product_row.get("id"):
        get_supabase().table("products").update({"mascot_asset_path": storage_path}).eq(
            "id", product_row["id"]
        ).execute()

    return image_bytes
