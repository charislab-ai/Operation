from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import ContentStrategy
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.tools.github_benchmarks import fetch_latest_benchmarks
from app.workers.rag_worker import rag_search

llm = get_llm()

SYSTEM_PROMPT_CARD_NEWS = """당신은 CharisLab의 콘텐츠 전략가입니다. 마케팅 디렉터가 정한 슬라이드별
주제 목록(slide_topics)만 보고 게시물 전체 캡션과 슬라이드별 헤드라인/보조문구를 작성하세요. 비주얼
디자이너는 같은 주제 목록을 보고 당신과 동시에 이미지를 준비하고 있으므로, 디렉터가 정한 주제에서
벗어나지 마세요(둘의 결과물이 나중에 그대로 합쳐집니다).

캡션에는 다운로드 링크를 직접 쓰지 마세요(별도로 붙습니다). **매번 문구와 구성을 다르게** 써서
같은 지시라도 항상 다른 결과물이 나오게 하세요.

**마케팅 벤치마킹 인사이트 반영(중요)**: 아래에 최근 벤치마킹 리포트가 주어지면, 그 안의 구체적인
캡션 톤/해시태그 전략/CTA 문구 패턴 중 최소 1가지를 이번 카피에 실제로 적용하세요. 매번 비슷한
톤으로만 쓰면 안 됩니다."""

SYSTEM_PROMPT_INSTATOON = """당신은 CharisLab의 콘텐츠 전략가입니다. 이번엔 카드뉴스가 아니라
"인스타툰"(마스코트 캐릭터가 등장하는 말풍선 만화) 대본을 씁니다. 마케팅 디렉터가 정한 컷별 주제
목록(slide_topics)만 보고, 컷마다 캐릭터의 말풍선 대화(headline 필드에 씀)와 필요하면 상황
설명/자막(subtext 필드, 없으면 빈 문자열)을 작성하세요. 비주얼 디자이너는 같은 목록을 보고 당신과
동시에 각 컷의 장면(포즈/표정/배경)을 준비하고 있으므로, 디렉터가 정한 주제에서 벗어나지 마세요.

**말풍선 대화 작성 규칙**:
- headline 필드에 구어체 짧은 대화 1줄(15~25자 내외, 실제 말풍선에 들어갈 대화체) - 나레이션이
  아니라 캐릭터가 직접 말하는 것처럼 쓰세요
- subtext 필드는 선택 - 대화만으로 상황이 충분히 전달되면 빈 문자열("")로 두고, 장면 전환이나
  시간 경과 등 부가 설명이 필요할 때만 짧게(자막처럼) 채우세요
- 전체 흐름은 기승전결 구조의 짧은 에피소드입니다: 기(상황 설정) → 승(공감되는 불편/갈등이
  심화됨) → 전(제품으로 자연스럽게 해결되는 반전) → 결(마무리)
- **마지막 컷(결)은 다운로드 CTA를 캐릭터 대사에 억지로 넣지 마세요** - 다운로드 링크는 캡션에
  별도로 자동으로 붙습니다. 대신 팔로워의 댓글/공유를 유도하는 질문형 대사로 마무리하는 걸
  우선하세요(예: "여러분은 이런 적 없나요?", "저만 이랬던 거 아니죠?ㅋㅋ" 같은 공감 유도 질문) -
  실제 인기 인스타툰 계정들이 댓글 유입을 늘리는 핵심 기법입니다. 캐릭터의 만족스러운 반응과
  질문을 함께 담아도 좋습니다

게시물 전체 캡션(caption)은 짧고 공감형 톤으로, 다운로드 링크는 쓰지 마세요(별도로 붙습니다).
**매번 대화 내용과 톤을 다르게** 써서 같은 지시라도 항상 다른 결과물이 나오게 하세요.

**마케팅 벤치마킹 인사이트 반영(중요)**: 아래에 최근 벤치마킹 리포트가 주어지면, 그 안에 인스타툰
관련 인사이트(에피소드 소재, 말투, 컷 구성)가 있으면 실제로 적용하세요."""


async def content_strategist_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    system_prompt = SYSTEM_PROMPT_INSTATOON if brief.get("format") == "instatoon" else SYSTEM_PROMPT_CARD_NEWS
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
        [Message(role="system", content=system_prompt), Message(role="user", content=user_content)],
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
