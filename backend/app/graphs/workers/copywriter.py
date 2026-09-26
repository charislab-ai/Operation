"""카피라이터 - 카드 안에 들어가는 짧은 문구(헤드라인/보조문구)만 전담한다.

Why 분리: 예전엔 "콘텐츠 전략가" 한 명이 캡션(피드에 노출되는 긴 글)과 카드 안 문구(15자 훅)를
같이 썼다. 두 글은 평가 기준이 완전히 다르다 - 캡션은 도달·저장·댓글(발견성)을 만드는 글이고,
카드 안 문구는 스와이프를 멈추게 하는 짧은 훅이다. 한 사람이 둘 다 쓰면 둘 다 평범해진다.
자료도 역할별로 잘라서 받는다(benchmark_slice) - 해시태그 인사이트는 여기서 안 본다.
"""

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import CopyPlan
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import (
    addressing_note,
    benchmark_slice,
    brand_book,
    canonical_product,
    fetch_products,
    original_ceo_text,
)
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.tools.github_benchmarks import fetch_latest_benchmarks

llm = get_llm()

SYSTEM_PROMPT_CARD_NEWS = """당신은 CharisLab의 카피라이터입니다. 카드뉴스 "이미지 안에 들어가는
문구"만 씁니다 - 게시물 캡션과 해시태그는 소셜 에디터가 따로 쓰고 있으니 신경 쓰지 마세요.

마케팅 디렉터가 정한 장별 주제(slide_topics)와 같은 개수·순서로 headline/subtext를 쓰세요.

작성 규칙:
- headline은 15자 내외. 스와이프를 멈추게 하는 게 유일한 목적이니, 설명하지 말고 찌르세요
  (나쁜 예 "ChaMu로 벨소리를 쉽게 만들 수 있어요" / 좋은 예 "아직도 기본 벨소리 쓰세요?")
- subtext는 25자 내외로 headline이 못 담은 구체성을 보탭니다(빈 문자열도 허용)
- 1번 장은 가장 강한 훅, 마지막 장은 행동을 부르는 문구로 끝내세요
- 같은 문장 구조를 여러 장에서 반복하지 마세요(전부 "~하세요"로 끝나면 안 됨)
- 브랜드북의 톤앤보이스를 지키고, 금지 표현은 절대 쓰지 마세요
- **매번 다르게 쓰세요** - 같은 지시라도 지난 회차와 같은 문구가 나오면 실패입니다"""

SYSTEM_PROMPT_INSTATOON = """당신은 CharisLab의 카피라이터입니다. 이번엔 인스타툰(마스코트가
등장하는 말풍선 만화)의 "대사"를 씁니다 - 캡션은 소셜 에디터가 따로 씁니다.

컷별 주제(slide_topics)와 같은 개수·순서로 쓰세요:
- headline = 말풍선에 들어갈 구어체 대사 1줄(15~25자). 나레이션이 아니라 캐릭터가 하는 말
- subtext = 자막/상황 설명(선택). 대사만으로 충분하면 빈 문자열("")
- 전체는 기승전결의 짧은 에피소드: 기(상황) → 승(불편이 심해짐) → 전(제품으로 해결) → 결(마무리)
- **마지막 컷에 다운로드 CTA를 억지로 넣지 마세요**(링크는 캡션에 자동으로 붙습니다). 대신
  댓글을 부르는 질문형 대사로 끝내세요("여러분도 이런 적 없어요?") - 실제 인기 인스타툰의
  댓글 유입 핵심 기법입니다
- 브랜드북의 톤앤보이스를 지키고, 금지 표현은 쓰지 마세요"""


async def copywriter_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    is_instatoon = brief.get("format") == "instatoon"
    system_prompt = SYSTEM_PROMPT_INSTATOON if is_instatoon else SYSTEM_PROMPT_CARD_NEWS
    run_id = start_run("Copywriter", {"slide_topics": brief["slide_topics"]}, thread_id=thread_id)

    product_row = fetch_products().get(canonical_product(brief["product"]))
    reports = await fetch_latest_benchmarks(limit=2)
    insights = benchmark_slice(reports, "copy")

    user_content = (
        f"[CEO 원본 지시문]\n{original_ceo_text(state)}{addressing_note(state, 'copywriter')}\n\n"
        f"{brand_book(product_row)}\n\n"
        f"제품: {brief['product']} / 채널: {brief['channel']}\n"
        f"{'컷' if is_instatoon else '슬라이드'} 주제({len(brief['slide_topics'])}개, 이 순서 그대로):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(brief["slide_topics"]))
        + (f"\n\n[벤치마킹 - 카피/훅 관련 발췌]\n{insights}" if insights else "")
    )

    plan = await llm.complete_structured(
        [Message(role="system", content=system_prompt), Message(role="user", content=user_content)],
        CopyPlan,
        thread_id=thread_id,
        agent_name="Copywriter",
    )

    result = plan.model_dump()
    finish_run(run_id, result)
    return {
        "copy_plan": result,
        "messages": [{"role": "assistant", "content": f"[Copywriter] 카드 문구 작성 완료 ({len(plan.slides)}장)"}],
    }
