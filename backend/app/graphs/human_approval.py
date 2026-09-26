from typing import Literal

from langgraph.graph import END
from langgraph.types import interrupt

from app.graphs.state import OSState

ApprovalKind = Literal["marketing", "dev"]


def _marketing_payload(state: OSState) -> dict:
    post = state.get("marketing_post", {})
    return {
        "type": "marketing_post_approval",
        "product": post.get("product"),
        "channel": post.get("channel"),
        "format": post.get("format", "card_news"),
        "caption": post.get("caption"),
        "slides": post.get("slides", []),
        "image_urls": post.get("image_urls", []),
        "video_url": post.get("video_url"),  # 쇼츠/릴스 - 결재 화면에서 함께 확인
        "director_notes": post.get("director_notes"),
        # 브랜드 QA가 완성 카드를 직접 보고 남긴 검수 소견 - CEO가 결재 전에 같이 본다.
        "qa_summary": (state.get("qa_report") or {}).get("summary"),
        "qa_issues": (state.get("qa_report") or {}).get("issues", []),
    }


def _dev_payload(state: OSState) -> dict:
    proposal = state.get("dev_proposal", {})
    return {
        "type": "dev_proposal_approval",
        "title": proposal.get("title"),
        "summary": proposal.get("summary"),
        "files_affected": proposal.get("files_affected", []),
        "code_sketch": proposal.get("code_sketch"),
        "pr_description": proposal.get("pr_description"),
    }


_PAYLOAD_BUILDERS = {"marketing": _marketing_payload, "dev": _dev_payload}


def make_approval_node(kind: ApprovalKind):
    """kind별로 독립된 승인 노드를 만든다. pm/marketing/dev가 같은 노드를 공유하면 병렬 실행 시
    LangGraph가 그 노드를 여러 선행자를 기다리는 조인(join)으로 취급해 상태가 섞여버리므로
    (어떤 Worker의 결과인지 구분 불가) 반드시 노드 자체를 분리해야 한다."""

    async def node(state: OSState) -> dict:
        decision = interrupt(_PAYLOAD_BUILDERS[kind](state))
        decision_value = decision.get("decision", "rejected") if isinstance(decision, dict) else "rejected"
        comment = decision.get("comment", "") if isinstance(decision, dict) else ""
        edited_post = decision.get("edited_post") if isinstance(decision, dict) else None
        update: dict = {
            "decisions": {kind: decision_value},
            "revision_notes": {kind: comment} if decision_value == "revision" and comment else {},
            "messages": [
                {"role": "user", "content": f"[텔레그램 승인 응답:{kind}] {decision_value} {comment}".strip()}
            ],
        }
        # 슬라이드 편집기에서 CEO가 직접 고친 내용이 있으면 그걸 최종본으로 삼는다.
        # Why 이 경로: 그래프 밖에서 aupdate_state로 상태를 덮어쓰면 대기 중인 interrupt의 id가
        # 바뀌어 저장해둔 interrupt_id로는 재개할 수 없게 된다(그럼 승인이 새 카드를 또 만든다).
        # 재개 값에 실어 보내 승인 노드 자신이 상태를 쓰게 하면 그 위험이 없다.
        if kind == "marketing" and isinstance(edited_post, dict) and edited_post.get("image_urls"):
            update["marketing_post"] = edited_post
        return update

    return node


#  보완(revision) 선택 시 재진입할 노드. 기본은 "{kind}_worker"지만 marketing은 팀 구조라
# 브리핑 노드부터 다시 시작해야 한다(디렉터가 보완 사유를 반영한 새 브리핑을 써야 전략가/디자이너가
# 다시 맞물려 작업할 수 있음).
_REVISION_RESTART_NODE: dict[ApprovalKind, str] = {
    "marketing": "marketing_director_brief",
    "dev": "dev_worker",
}


# 보완 사유에서 특정 직원을 지목했을 때 그 직원만 다시 일하도록 보내는 노드.
# Why: "카피라이터, 1장 제목만 더 세게"처럼 한 사람에게 내리는 보완인데도 예전엔 브리핑부터
# 전원이 다시 돌아 이미지까지 전부 새로 생성됐다(이미지 3~5장 비용이 그대로 재발생). 지목된
# 직원만 다시 돌리면 나머지 산출물은 state에 그대로 남아 합성 때 재사용되고, 사진 지시문이
# 안 바뀌었으므로 원본 사진도 재사용된다(marketing_director.py::_reusable_source → 이미지 비용 0).
_SPECIALIST_NODES = {
    "copywriter": "copywriter",
    "social_editor": "social_editor",
    "photo_art_director": "photo_art_director",
    "layout_designer": "layout_designer",
}


def _marketing_revision_target(state: OSState) -> str:
    from app.graphs.workers._marketing_shared import detect_addressee

    note = state.get("revision_notes", {}).get("marketing") or ""
    addressed = detect_addressee(note)
    if not addressed:
        return "marketing_director_brief"
    # 이미 산출물이 있어야 그 사람만 다시 돌리는 게 의미가 있다(첫 실행이면 브리핑부터).
    if not state.get("marketing_post"):
        return "marketing_director_brief"
    return _SPECIALIST_NODES.get(addressed["agent_key"], "marketing_director_brief")


def make_route_after_approval(kind: ApprovalKind):
    def route(state: OSState) -> str:
        decision = state.get("decisions", {}).get(kind)
        if decision == "approved" and kind == "marketing":
            return "publish_worker"
        if decision == "revision":
            if kind == "marketing":
                return _marketing_revision_target(state)
            return _REVISION_RESTART_NODE[kind]
        return END

    return route
