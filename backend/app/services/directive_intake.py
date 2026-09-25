"""CEO 지시 생성의 핵심 로직 - 웹 컴포저(POST /directives, 멀티파트)와 텔레그램 "/지시" 명령
양쪽에서 동일하게 호출한다. 첨부 이미지/영상은 저장·표시되고 파일명/URL/캡션이 텍스트로
그래프에 전달될 뿐이며, 이 단계에서는 어떤 워커도 비전 모델로 내용을 분석하지 않는다
(범위 밖, 추후 별도 기능)."""

import mimetypes
import uuid
from dataclasses import dataclass

from app.db.supabase_client import get_supabase
from app.services.failures import record_graph_failure
from app.tools.telegram_bot import send_approval_request

DIRECTIVE_MEDIA_BUCKET = "directive-media"


@dataclass
class UploadedMediaRef:
    filename: str | None
    content: bytes
    content_type: str | None
    caption: str | None = None


def upload_one_media(supabase, thread_id: str, media: UploadedMediaRef) -> dict:
    """product_assets 업로드와 동일한 패턴 - Storage 키는 UUID만 사용(원본 파일명 버림,
    한글 파일명이면 InvalidKey 에러가 나기 때문)."""
    mime_type = media.content_type or mimetypes.guess_type(media.filename or "")[0] or "application/octet-stream"
    media_type = "video" if mime_type.startswith("video/") else "image"
    ext = mimetypes.guess_extension(mime_type) or (".mp4" if media_type == "video" else ".png")
    storage_path = f"{uuid.uuid4()}{ext}"

    bucket = supabase.storage.from_(DIRECTIVE_MEDIA_BUCKET)
    bucket.upload(storage_path, media.content, {"content-type": mime_type})
    url = bucket.get_public_url(storage_path)

    row = (
        supabase.table("directive_media")
        .insert(
            {
                "thread_id": thread_id,
                "storage_path": storage_path,
                "media_type": media_type,
                "caption": media.caption,
            }
        )
        .execute()
    )
    return {"id": row.data[0]["id"], "media_type": media_type, "url": url, "caption": media.caption}


def _augment_text(text: str, uploaded: list[dict]) -> str:
    """directives.ceo_directive에는 원본 text 그대로 저장하고, 그래프에는 첨부 참조를
    덧붙인 텍스트를 넘긴다 - 워커가 첨부물의 존재를 알 수 있게 하되 이미지/영상 내용 자체를
    분석하지는 않는다(범위 밖)."""
    if not uploaded:
        return text
    lines = [
        f"- {m['media_type']}: {m['url']}" + (f" ({m['caption']})" if m.get("caption") else "")
        for m in uploaded
    ]
    return f"{text}\n\n[첨부 파일]\n" + "\n".join(lines)


async def create_directive_and_run(graph, text: str, media: list[UploadedMediaRef]) -> dict:
    """POST /directives(멀티파트)와 텔레그램 "/지시" 명령이 공통으로 쓰는 지시 생성 로직.
    thread_id 발급 → directives 행 선등록(그래프 실행 도중 문제가 생겨도 목록엔 항상 남도록) →
    첨부 업로드 → 첨부 참조를 덧붙인 텍스트로 그래프 실행 → interrupt 있으면 승인 카드 발송."""
    supabase = get_supabase()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    supabase.table("directives").insert({"thread_id": thread_id, "ceo_directive": text}).execute()

    uploaded = [upload_one_media(supabase, thread_id, m) for m in media]
    augmented_text = _augment_text(text, uploaded)

    try:
        result = await graph.ainvoke({"ceo_directive": augmented_text, "messages": []}, config)
    except Exception as exc:
        # 실패를 조용히 삼키면 CEO 화면엔 "진행중"만 영원히 남는다 - 기록/알림 후 그대로 올려보낸다
        # (웹 제출이면 HTTP 응답으로도 에러가 보여야 하므로 재전파).
        await record_graph_failure(thread_id, exc)
        raise

    interrupts = result.get("__interrupt__")
    if not interrupts:
        return {"thread_id": thread_id, "status": "completed"}

    # Goal형 병렬 실행에서는 여러 부서가 동시에 승인을 기다릴 수 있어 interrupt가 여러 개 올 수 있다.
    for interrupt_obj in interrupts:
        interrupt_payload = interrupt_obj.value
        target_type = interrupt_payload.get("type", "task_plan_approval").removesuffix("_approval")

        approval = (
            supabase.table("approvals")
            .insert(
                {
                    "target_type": target_type,
                    "thread_id": thread_id,
                    "status": "pending",
                    "payload": interrupt_payload,
                    "interrupt_id": interrupt_obj.id,
                }
            )
            .execute()
        )
        approval_id = approval.data[0]["id"]

        message_id = await send_approval_request(approval_id, target_type, interrupt_payload)
        supabase.table("approvals").update({"telegram_msg_id": str(message_id)}).eq(
            "id", approval_id
        ).execute()

    return {"thread_id": thread_id, "status": "pending_approval"}
