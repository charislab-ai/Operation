from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


def _format_task_plan_card(payload: dict, footer: str) -> str:
    project_title = payload.get("project_title") or "(제목 없음)"
    tasks = payload.get("tasks", [])
    lines = [f"📋 {project_title}", ""]
    for t in tasks:
        lines.append(f"- [{t.get('dept')}] {t.get('title')} ({t.get('start_date')} ~ {t.get('end_date')})")
    lines.append("")
    lines.append(footer)
    return "\n".join(lines)


def _format_finance_entry_card(payload: dict, footer: str) -> str:
    lines = [
        "🧾 영수증 분개 확인",
        "",
        f"가맹점: {payload.get('merchant', '(알 수 없음)')}",
        f"일자: {payload.get('entry_date', '-')}",
        f"금액: {payload.get('amount', 0):,.0f}원",
        f"계정: {payload.get('debit_account', '-')} / {payload.get('credit_account', '-')}",
        f"부가세 포함: {'예' if payload.get('vat_flag') else '아니오'}",
        "",
        footer,
    ]
    return "\n".join(lines)


def _format_marketing_post_card(payload: dict, footer: str) -> str:
    slides = payload.get("slides", [])
    image_urls = payload.get("image_urls", [])
    lines = [
        "📣 마케팅 콘텐츠 확인",
        "",
        f"제품: {payload.get('product', '-')}",
        f"채널: {payload.get('channel', '-')}",
        f"카드뉴스 {len(image_urls)}장",
        "",
    ]
    for i, slide in enumerate(slides):
        lines.append(f"[{i + 1}장] {slide.get('headline', '-')} — {slide.get('subtext', '-')}")
    lines.append("")
    lines.append(payload.get("caption", ""))
    lines.append("")
    for i, url in enumerate(image_urls):
        lines.append(f"이미지 {i + 1}: {url}")
    lines.append("")
    lines.append(footer)
    return "\n".join(lines)


def _format_dev_proposal_card(payload: dict, footer: str) -> str:
    files = payload.get("files_affected", [])
    lines = [
        "🛠️ 코드 제안 확인",
        "",
        f"제목: {payload.get('title', '-')}",
        f"요약: {payload.get('summary', '-')}",
        "",
        "영향 파일:",
        *(f"- {f}" for f in files),
        "",
        "PR 초안:",
        payload.get("pr_description", ""),
        "",
        footer,
    ]
    return "\n".join(lines)


_CARD_FORMATTERS = {
    "task_plan": _format_task_plan_card,
    "finance_entry": _format_finance_entry_card,
    "marketing_post": _format_marketing_post_card,
    "dev_proposal": _format_dev_proposal_card,
}

# task_plan/dev_proposal은 승인/보완/반려 3분기(보완 시 각 Worker 재작업),
# finance_entry/marketing_post는 재작업 대상 워커가 없어(또는 단순화 목적으로) 2분기만 둔다.
_CARD_BUTTONS = {
    "task_plan": [("✅ 승인", "approved"), ("✏️ 보완", "revision"), ("❌ 반려", "rejected")],
    "finance_entry": [("✅ 승인", "approved"), ("❌ 반려", "rejected")],
    "marketing_post": [("✅ 승인", "approved"), ("❌ 반려", "rejected")],
    "dev_proposal": [("✅ 승인", "approved"), ("✏️ 보완", "revision"), ("❌ 반려", "rejected")],
}

_DECISION_LABEL = {"approved": "✅ 승인 처리됨", "rejected": "❌ 반려 처리됨", "revision": "✏️ 보완 요청 처리중..."}


async def send_approval_request(approval_id: str, target_type: str, payload: dict) -> int:
    format_card = _CARD_FORMATTERS[target_type]
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label, callback_data=f"{target_type}:{approval_id}:{decision}")
                for label, decision in _CARD_BUTTONS[target_type]
            ]
        ]
    )
    message = await get_bot().send_message(
        chat_id=settings.telegram_ceo_chat_id,
        text=format_card(payload, "승인하시겠습니까?"),
        reply_markup=keyboard,
    )
    return message.message_id


async def acknowledge_decision(message_id: int, target_type: str, payload: dict, decision: str) -> None:
    """원본 카드 내용은 그대로 두고, 하단 문구만 처리 결과로 바꾸고 버튼을 제거한다 —
    제목/내용과 처리결과가 한 메시지에 보이도록 (별도 메시지로 분리하지 않음).
    """
    format_card = _CARD_FORMATTERS[target_type]
    footer = _DECISION_LABEL.get(decision, decision)
    await get_bot().edit_message_text(
        chat_id=settings.telegram_ceo_chat_id,
        message_id=message_id,
        text=format_card(payload, footer),
        reply_markup=InlineKeyboardMarkup([]),
    )
