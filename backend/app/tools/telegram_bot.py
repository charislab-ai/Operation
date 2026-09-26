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
    is_instatoon = payload.get("format") == "instatoon"
    unit = "컷" if is_instatoon else "장"
    lines = [
        "📣 마케팅 콘텐츠 확인",
        "",
        f"제품: {payload.get('product', '-')}",
        f"채널: {payload.get('channel', '-')}",
        f"형식: {'인스타툰' if is_instatoon else '카드뉴스'}",
        f"{'인스타툰' if is_instatoon else '카드뉴스'} {len(image_urls)}{unit}",
        "",
    ]
    for i, slide in enumerate(slides):
        lines.append(f"[{i + 1}{unit}] {slide.get('headline', '-')} — {slide.get('subtext', '-')}")
    lines.append("")
    lines.append(payload.get("caption", ""))
    lines.append("")
    for i, url in enumerate(image_urls):
        lines.append(f"이미지 {i + 1}: {url}")
    if payload.get("director_notes"):
        lines.append("")
        lines.append(f"🎬 디렉터 소견: {payload['director_notes']}")
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

# finance_entry는 재작업 대상 워커가 없어 승인/반려 2분기만 둔다. 나머지는 보완(revision) 포함 3분기.
_CARD_BUTTONS = {
    "task_plan": [("✅ 승인", "approved"), ("✏️ 보완", "revision"), ("❌ 반려", "rejected")],
    "finance_entry": [("✅ 승인", "approved"), ("❌ 반려", "rejected")],
    "marketing_post": [("✅ 승인", "approved"), ("✏️ 보완", "revision"), ("❌ 반려", "rejected")],
    "dev_proposal": [("✅ 승인", "approved"), ("✏️ 보완", "revision"), ("❌ 반려", "rejected")],
}

_DECISION_LABEL = {"approved": "✅ 승인 처리됨", "rejected": "❌ 반려 처리됨", "revision": "✏️ 보완 반영 완료", "cancelled": "🛑 CEO가 강제 종료함"}


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


_COMMENT_PROMPT = {
    "revision": "✏️ 보완 사유를 알려주세요 — 이 메시지에 답장(reply)하거나, 그냥 다음 메시지로 보내셔도 됩니다",
    "rejected": "❌ 반려 사유를 알려주세요 — 이 메시지에 답장(reply)하거나 그냥 다음 메시지로 보내세요 (사유 없이 반려하려면 '없음')",
}


async def prompt_for_comment(message_id: int, target_type: str, payload: dict, decision: str = "revision") -> None:
    """보완/반려 버튼을 누르면 원본 카드 내용은 유지한 채 하단 문구를 사유 입력 안내로 바꾸고
    버튼을 지운다 — CEO가 답장(또는 그냥 다음 메시지)으로 사유를 보내면 app/api/telegram.py가
    매칭한다. 반려도 사유를 받을 수 있어야 한다는 CEO 요청으로 decision별 안내 문구를 분리했다."""
    format_card = _CARD_FORMATTERS[target_type]
    await get_bot().edit_message_text(
        chat_id=settings.telegram_ceo_chat_id,
        message_id=message_id,
        text=format_card(payload, _COMMENT_PROMPT.get(decision, _COMMENT_PROMPT["revision"])),
        reply_markup=InlineKeyboardMarkup([]),
    )


async def notify_ceo(text: str) -> None:
    """CEO에게 짧은 안내/경고 메시지를 보낸다 - 조용히 무시되던 상황들(이미 처리된 카드에
    답장, 매칭 실패 등)에 반드시 피드백을 주기 위함."""
    await get_bot().send_message(chat_id=settings.telegram_ceo_chat_id, text=text)


async def mark_processing(message_id: int, target_type: str, payload: dict) -> None:
    """결정 버튼을 누른 "직후"(실제 처리 시작 전) 즉시 카드를 "처리 중"으로 바꾸고 버튼을
    없앤다 - 처리(재생성 등)가 몇 분씩 걸리는 동안 버튼이 살아있으면 CEO가 다시 눌러서 같은
    결정이 중복 처리되는 문제가 실측으로 확인됐다. acknowledge_decision은 처리가 끝난 뒤
    최종 결과로 다시 한 번 갱신한다."""
    format_card = _CARD_FORMATTERS[target_type]
    await get_bot().edit_message_text(
        chat_id=settings.telegram_ceo_chat_id,
        message_id=message_id,
        text=format_card(payload, "⏳ 처리 중입니다... 잠시만 기다려주세요"),
        reply_markup=InlineKeyboardMarkup([]),
    )


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


async def send_hire_recommendation(employee: dict, readiness: dict) -> int:
    """입사 예정 직원의 입사 조건이 채워졌을 때 CEO에게 보내는 채용 추천 카드.

    조건이 얼마나 쌓여야 하는지를 CEO가 계속 지켜볼 필요 없이, 시스템이 먼저 알리고 버튼
    하나로 입사시킬 수 있게 한다(app/services/hiring.py). 콜백 형식은 기존 승인 카드와 같은
    "{target_type}:{id}:{decision}" 3단 구조를 그대로 쓴다(app/api/telegram.py 파서 공용)."""
    lines = [
        f"🧑‍💼 입사 추천 — {employee['name']} ({employee['rank']} · {employee['title']})",
        "",
        "입사 조건이 모두 채워졌습니다:",
    ]
    for check in readiness.get("checks", []):
        lines.append(f"  ✅ {check['label']} {check['raw']}{check['unit']} (기준 {check['needed']}{check['unit']})")
    lines += ["", f"맡을 일: {employee['responsibilities']}", "", readiness.get("why", "")]

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🙌 입사시키기", callback_data=f"hire:{employee['agent_key']}:accept"),
                InlineKeyboardButton("나중에", callback_data=f"hire:{employee['agent_key']}:later"),
            ]
        ]
    )
    message = await get_bot().send_message(
        chat_id=settings.telegram_ceo_chat_id, text="\n".join(lines), reply_markup=keyboard
    )
    return message.message_id


async def acknowledge_hire(message_id: int, employee: dict, accepted: bool) -> None:
    """입사 추천 카드의 버튼을 누른 뒤 카드를 결과 문구로 바꾸고 버튼을 지운다."""
    text = (
        f"🙌 {employee['name']}({employee['title']}) 입사 완료 — 다음 지시부터 업무에 투입됩니다."
        if accepted
        else f"🕓 {employee['name']}({employee['title']}) 입사 보류 — 직원 화면에서 언제든 입사시킬 수 있습니다."
    )
    await get_bot().edit_message_text(
        chat_id=settings.telegram_ceo_chat_id,
        message_id=message_id,
        text=text,
        reply_markup=InlineKeyboardMarkup([]),
    )
