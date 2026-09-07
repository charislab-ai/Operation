from typing import Literal

from langgraph.graph import END
from langgraph.types import interrupt

from app.graphs.state import OSState

ApprovalKind = Literal["pm", "marketing", "dev"]


def _pm_payload(state: OSState) -> dict:
    wbs = state.get("wbs_plan", {})
    return {
        "type": "task_plan_approval",
        "project_title": wbs.get("project_title"),
        "tasks": wbs.get("tasks", []),
    }


def _marketing_payload(state: OSState) -> dict:
    post = state.get("marketing_post", {})
    return {
        "type": "marketing_post_approval",
        "product": post.get("product"),
        "channel": post.get("channel"),
        "caption": post.get("caption"),
        "slides": post.get("slides", []),
        "image_urls": post.get("image_urls", []),
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


_PAYLOAD_BUILDERS = {"pm": _pm_payload, "marketing": _marketing_payload, "dev": _dev_payload}


def make_approval_node(kind: ApprovalKind):
    """kind별로 독립된 승인 노드를 만든다. pm/marketing/dev가 같은 노드를 공유하면 병렬 실행 시
    LangGraph가 그 노드를 여러 선행자를 기다리는 조인(join)으로 취급해 상태가 섞여버리므로
    (어떤 Worker의 결과인지 구분 불가) 반드시 노드 자체를 분리해야 한다."""

    async def node(state: OSState) -> dict:
        decision = interrupt(_PAYLOAD_BUILDERS[kind](state))
        decision_value = decision.get("decision", "rejected") if isinstance(decision, dict) else "rejected"
        comment = decision.get("comment", "") if isinstance(decision, dict) else ""
        return {
            "decisions": {kind: decision_value},
            "messages": [
                {"role": "user", "content": f"[텔레그램 승인 응답:{kind}] {decision_value} {comment}".strip()}
            ],
        }

    return node


def make_route_after_approval(kind: ApprovalKind):
    def route(state: OSState) -> str:
        decision = state.get("decisions", {}).get(kind)
        if decision == "approved" and kind == "marketing":
            return "publish_worker"
        if decision == "revision":
            return f"{kind}_worker"
        return END

    return route
