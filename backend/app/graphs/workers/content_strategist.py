from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import ContentStrategy
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.tools.github_benchmarks import fetch_latest_benchmarks
from app.workers.rag_worker import rag_search

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 콘텐츠 전략가입니다. 마케팅 디렉터가 정한 슬라이드별 주제
목록(slide_topics)만 보고 게시물 전체 캡션과 슬라이드별 헤드라인/보조문구를 작성하세요. 비주얼
디자이너는 같은 주제 목록을 보고 당신과 동시에 이미지를 준비하고 있으므로, 디렉터가 정한 주제에서
벗어나지 마세요(둘의 결과물이 나중에 그대로 합쳐집니다).

캡션에는 다운로드 링크를 직접 쓰지 마세요(별도로 붙습니다). **매번 문구와 구성을 다르게** 써서
같은 지시라도 항상 다른 결과물이 나오게 하세요.

**마케팅 벤치마킹 인사이트 반영(중요)**: 아래에 최근 벤치마킹 리포트가 주어지면, 그 안의 구체적인
캡션 톤/해시태그 전략/CTA 문구 패턴 중 최소 1가지를 이번 카피에 실제로 적용하세요. 매번 비슷한
톤으로만 쓰면 안 됩니다."""


async def content_strategist_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    run_id = start_run("ContentStrategist", {"slide_topics": brief["slide_topics"]}, thread_id=thread_id)

    query = f"{brief['product']} {' '.join(brief['slide_topics'])}"
    related_docs = await rag_search(query, limit=3)
    doc_context = (
        "\n\n".join(f"[제품 특징 문서] {d['content']}" for d in related_docs)
        if related_docs
        else "(참고할 제품 문서 없음)"
    )

    benchmarks = await fetch_latest_benchmarks(limit=2)
    benchmark_context = (
        "\n\n".join(f"[최근 마케팅 벤치마킹 리포트]\n{b}" for b in benchmarks)
        if benchmarks
        else "(벤치마킹 리포트 없음)"
    )

    user_content = (
        f"제품: {brief['product']}\n채널: {brief['channel']}\n"
        f"슬라이드 주제({len(brief['slide_topics'])}개, 이 순서 그대로 작성):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(brief["slide_topics"]))
        + f"\n\n{doc_context}\n\n{benchmark_context}"
    )

    strategy = await llm.complete_structured(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user_content)],
        ContentStrategy,
        thread_id=thread_id,
        agent_name="ContentStrategist",
    )

    result = strategy.model_dump()
    finish_run(run_id, result)
    return {
        "content_strategy": result,
        "messages": [{"role": "assistant", "content": f"[ContentStrategist] 카피 작성 완료 ({len(strategy.slides)}장)"}],
    }
