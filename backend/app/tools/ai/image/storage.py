import uuid

from app.db.supabase_client import get_supabase

MARKETING_IMAGES_BUCKET = "marketing-images"


def upload_marketing_image(image_bytes: bytes) -> str:
    """합성된 마케팅 카드 이미지를 공개 버킷에 올리고 공개 URL을 반환한다.

    Meta Graph API 등 외부 서비스가 fetch할 수 있어야 하므로(내부 서명 URL이 아니라) 공개 버킷 사용.
    """
    storage_path = f"{uuid.uuid4()}.png"
    bucket = get_supabase().storage.from_(MARKETING_IMAGES_BUCKET)
    bucket.upload(storage_path, image_bytes, {"content-type": "image/png"})
    return bucket.get_public_url(storage_path)
