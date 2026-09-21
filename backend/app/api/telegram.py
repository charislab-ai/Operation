import asyncio

from fastapi import APIRouter, HTTPException, Request
from telegram import BotCommand

from app.config import settings
from app.db.supabase_client import get_supabase
from app.graphs import task_registry
from app.services.approvals import GRAPH_BASED_TARGET_TYPES, claim_approval, decide_finance_entry, resume_approval
from app.services.directive_intake import UploadedMediaRef, create_directive_and_run
from app.tools.telegram_bot import get_bot, mark_processing, prompt_for_comment, send_approval_request

router = APIRouter(prefix="/telegram", tags=["telegram"])

DIRECTIVE_COMMAND = "/지시"

# 텔레그램은 응답이 늦으면(처리가 몇 분씩 걸리는 마케팅 재생성 등) 같은 update를 재전송한다 -
# update_id는 재전송돼도 동일하므로 최근 처리한 것만 기억해두면 중복 처리를 막을 수 있다.
# approval 쪽은 claim_approval(원자적 락)로 이미 막히지만, "/지시"로 새 지시를 만드는 경로는
# 매번 새 row를 만들어서 같은 보호가 없어 이 범용 가드로 함께 막는다. 프로세스 재시작하면
# 비워지는데(Railway 단일 프로세스, 인메모리) 재전송은 보통 초~분 단위라 문제 없음.
_seen_update_ids: set[int] = set()
_SEEN_UPDATE_IDS_MAX = 500


def _already_processed(update_id: int | None) -> bool:
    if update_id is None:
        return False
    if update_id in _seen_update_ids:
        return True
    _seen_update_ids.add(update_id)
    if len(_seen_update_ids) > _SEEN_UPDATE_IDS_MAX:
        _seen_update_ids.pop()
    return False


def _is_from_ceo(update: dict) -> bool:
    """텔레그램 웹훅의 secret_token 검증은 "텔레그램 서버에서 온 요청"만 보장할 뿐, "CEO 본인
    채팅방에서 온 메시지"인지는 보장하지 않는다 - 봇 사용자명을 아는 누구나 메시지/버튼 클릭을
    보낼 수 있다. /지시 명령으로 새 지시를 만들 수 있게 되는 만큼 발신자 채팅방을 확인한다."""
    message = update.get("message") or (update.get("callback_query") or {}).get("message")
    chat_id = (message or {}).get("chat", {}).get("id")
    return str(chat_id) == str(settings.telegram_ceo_chat_id)


async def _handle_graph_resume(
    request: Request, supabase, approval_id: str, decision: str, comment: str = ""
) -> None:
    """모든 텔레그램 진입점(승인/반려 버튼, 보완 답장, 보완 폴백)이 이 함수를 거친다.

    claim_approval로 먼저 선점(원자적)한 뒤에만 실제 처리를 시작한다 - 이미 처리
    중이거나 끝난 approval이면 조용히 무시(중복 처리 방지, 실측으로 확인된 버그의 핵심 수정).
    실제 처리(그래프 재개, 몇 분씩 걸릴 수 있음)는 백그라운드로 돌려서 웹훅 응답을 즉시
    돌려준다 - 텔레그램이 응답 지연으로 같은 업데이트를 재전송하는 것도 함께 방지된다.
    """
    thread_row = (
        supabase.table("approvals").select("thread_id").eq("id", approval_id).single().execute()
    )
    thread_id_hint = thread_row.data.get("thread_id") if thread_row.data else None
    if thread_id_hint:
        directive_row = (
            supabase.table("directives")
            .select("paused_at, terminated_at")
            .eq("thread_id", thread_id_hint)
            .execute()
        )
        if directive_row.data and (directive_row.data[0].get("paused_at") or directive_row.data[0].get("terminated_at")):
            return  # 정지/강제종료된 지시 - 텔레그램 버튼으로도 처리 못 하게 조용히 무시

    claimed = await claim_approval(supabase, approval_id)
    if not claimed:
        return
    message_id = claimed.get("telegram_msg_id")
    target_type = claimed.get("target_type")
    payload = claimed.get("payload")
    if message_id and target_type and payload:
        try:
            await mark_processing(int(message_id), target_type, payload)
        except Exception:
            pass  # 카드 갱신 실패는 무시 - 실제 처리는 계속 진행

    async def _run() -> None:
        try:
            await resume_approval(request.app.state.graph, supabase, approval_id, decision, comment)
        except Exception:
            pass  # 백그라운드 태스크 - 예외를 삼켜서 미처리 태스크 경고로 그치게 함(TODO: 로깅)

    task = asyncio.create_task(_run())
    thread_id = claimed.get("thread_id")
    if thread_id:
        task_registry.register(thread_id, task)


async def _handle_finance_entry(supabase, approval_id: str, decision: str) -> None:
    claimed = await claim_approval(supabase, approval_id)
    if not claimed:
        return
    await decide_finance_entry(supabase, approval_id, decision)


async def _handle_revision_button(supabase, approval_id: str) -> None:
    """보완 버튼: 아직 재개하지 않고 CEO의 사유 답장을 기다린다(카드를 답장 안내로 바꿔둠)."""
    row = (
        supabase.table("approvals")
        .select("telegram_msg_id, payload, target_type")
        .eq("id", approval_id)
        .single()
        .execute()
    )
    supabase.table("approvals").update({"awaiting_comment": True}).eq("id", approval_id).execute()
    message_id = row.data.get("telegram_msg_id")
    if message_id:
        await prompt_for_comment(int(message_id), row.data["target_type"], row.data["payload"])


async def _handle_comment_reply_fallback(request: Request, supabase, comment: str) -> None:
    """CEO가 텔레그램의 "답장(reply)" 제스처를 안 쓰고 그냥 새 메시지로 보완 사유를 보낸 경우를
    위한 안전장치(실측: 답장 없이 보내면 무시되어 보완이 멈춰버리는 문제 확인됨). 지금 보완 사유를
    기다리는 중인(awaiting_comment=True, pending) approval이 정확히 1건일 때만 그 건으로 매칭한다 -
    여러 건이 동시에 대기 중이면(Goal형 병렬 실행) 어느 카드인지 알 수 없으므로 안전하게 무시한다."""
    rows = (
        supabase.table("approvals")
        .select("id, target_type")
        .eq("awaiting_comment", True)
        .eq("status", "pending")
        .execute()
    ).data
    if len(rows) != 1:
        return

    approval_id = rows[0]["id"]
    target_type = rows[0]["target_type"]
    supabase.table("approvals").update({"awaiting_comment": False}).eq("id", approval_id).execute()

    if target_type in GRAPH_BASED_TARGET_TYPES:
        await _handle_graph_resume(request, supabase, approval_id, "revision", comment)


def _extract_directive_command_text(message: dict) -> str | None:
    """텍스트 또는 캡션이 "/지시"로 시작하면 나머지 내용을 반환한다(그룹챗 대비 "/지시@BotName"도
    허용 - 이 봇은 1:1 CEO 채팅 전용이라 무관하지만 방어적으로 처리). 매칭 안 되면 None."""
    for raw in (message.get("text"), message.get("caption")):
        if not raw:
            continue
        token = raw.split(maxsplit=1)[0]
        command = token.split("@")[0]
        if command == DIRECTIVE_COMMAND:
            return raw[len(token) :].strip()
    return None


async def _download_telegram_media(message: dict) -> UploadedMediaRef | None:
    """/지시 명령에 사진/영상이 첨부돼 있으면 다운로드해서 UploadedMediaRef로 만든다."""
    photo_list = message.get("photo")
    video = message.get("video")
    file_id = photo_list[-1]["file_id"] if photo_list else (video["file_id"] if video else None)
    if not file_id:
        return None
    tg_file = await get_bot().get_file(file_id)
    content = bytes(await tg_file.download_as_bytearray())
    content_type = "video/mp4" if video else "image/jpeg"
    return UploadedMediaRef(filename=None, content=content, content_type=content_type)


async def _handle_directive_command(request: Request, message: dict, directive_text: str) -> None:
    """"/지시 <내용>" 명령 - 보완 대기 중인 카드가 있어도 무시하고 항상 새 지시로 처리한다."""
    media_ref = await _download_telegram_media(message)
    media = [media_ref] if media_ref else []

    graph = request.app.state.graph
    result = await create_directive_and_run(graph, directive_text, media)
    await get_bot().send_message(
        chat_id=settings.telegram_ceo_chat_id,
        text=f"✅ 지시가 등록되었습니다 (상태: {result['status']})",
    )


async def _handle_comment_reply(request: Request, supabase, reply_to_message_id: int, comment: str) -> None:
    """CEO가 보완 안내 카드에 답장으로 사유를 남기면, 그 카드에 해당하는 approval을 찾아
    실제로 그래프를 revision으로 재개한다. telegram_msg_id로 매칭하므로 병렬로 여러 카드가
    동시에 대기 중이어도(Goal형 병렬 실행) 정확히 그 카드만 처리된다."""
    row = (
        supabase.table("approvals")
        .select("id, target_type")
        .eq("telegram_msg_id", str(reply_to_message_id))
        .eq("awaiting_comment", True)
        .eq("status", "pending")
        .limit(1)
        .execute()
    )
    if not row.data:
        return  # 보완 대기 중이 아닌 메시지에 대한 답장 - 무시

    approval_id = row.data[0]["id"]
    target_type = row.data[0]["target_type"]
    supabase.table("approvals").update({"awaiting_comment": False}).eq("id", approval_id).execute()

    if target_type in GRAPH_BASED_TARGET_TYPES:
        await _handle_graph_resume(request, supabase, approval_id, "revision", comment)
    # finance_entry는 보완 버튼 자체가 없어(2분기) 이 경로를 타지 않는다.


@router.post("/webhook")
async def telegram_webhook(request: Request) -> dict:
    # 실배포 후 setWebhook(secret_token=...)으로 등록하면 텔레그램이 매 요청에 이 헤더를 실어보낸다.
    # 값이 비어있으면(로컬 개발, webhook 미등록 상태) 검사를 건너뛴다.
    if settings.telegram_webhook_secret:
        incoming = request.headers.get("x-telegram-bot-api-secret-token")
        if incoming != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="invalid webhook secret")

    update = await request.json()
    supabase = get_supabase()

    if _already_processed(update.get("update_id")):
        return {"ok": True}  # 텔레그램의 재전송(응답 지연 등) - 이미 처리한 update, 조용히 무시

    if not _is_from_ceo(update):
        return {"ok": True}  # CEO 본인 채팅방이 아니면 조용히 무시 (에러 응답은 정보를 흘림)

    callback_query = update.get("callback_query")
    if callback_query:
        try:
            await get_bot().answer_callback_query(callback_query["id"])
        except Exception:
            # 오래된/중복/테스트용 콜백이면 Telegram이 응답을 거부할 수 있다 — 버튼 스피너만 못 없앨 뿐
            # 아래 승인 처리 로직 자체는 계속 진행해야 하므로 무시한다.
            pass

        parts = callback_query.get("data", "").split(":")
        if len(parts) != 3:
            return {"ok": True}
        target_type, approval_id, decision = parts

        if decision == "revision":
            await _handle_revision_button(supabase, approval_id)
        elif target_type in GRAPH_BASED_TARGET_TYPES:
            await _handle_graph_resume(request, supabase, approval_id, decision)
        elif target_type == "finance_entry":
            await _handle_finance_entry(supabase, approval_id, decision)
        return {"ok": True}

    message = update.get("message")
    if message:
        directive_text = _extract_directive_command_text(message)
        if directive_text is not None:
            # "/지시" 명령은 보완 대기 상태와 무관하게 항상 새 지시 제출로 우선 처리한다.
            await _handle_directive_command(request, message, directive_text)
            return {"ok": True}

    reply_to = message.get("reply_to_message") if message else None
    if message and message.get("text"):
        if reply_to:
            await _handle_comment_reply(request, supabase, reply_to["message_id"], message["text"])
        else:
            await _handle_comment_reply_fallback(request, supabase, message["text"])

    return {"ok": True}
