from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import DevProposal
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.workers.rag_worker import rag_search

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 개발(CTO) 에이전트입니다. CEO의 지시를 분석해 코드 변경 제안을
작성하세요. 실제로 파일을 수정하거나 커밋하지 않습니다 — 검토용 제안(PR 초안)만 만듭니다.
관련 문서(RAG 검색 결과)가 주어지면 그 내용을 근거로 더 구체적인 제안을 작성하세요."""


async def dev_worker_node(state: OSState) -> dict:
    run_id = start_run("DevWorker", {"ceo_directive": state["ceo_directive"]})
    brief = state.get("worker_briefs", {}).get("dev") or state["ceo_directive"]

    related_docs = await rag_search(brief, limit=3)
    context = (
        "\n\n".join(f"[참고 문서] {d['content']}" for d in related_docs)
        if related_docs
        else "(관련 문서 없음)"
    )

    proposal = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"{brief}\n\n{context}"),
        ],
        DevProposal,
    )

    dev_proposal = proposal.model_dump()
    finish_run(run_id, dev_proposal)

    return {
        "dev_proposal": dev_proposal,
        "messages": [{"role": "assistant", "content": f"[Dev] 코드 제안 생성: {proposal.title}"}],
    }
