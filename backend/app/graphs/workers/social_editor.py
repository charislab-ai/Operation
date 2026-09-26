"""소셜 에디터 - 피드에 노출되는 캡션과 해시태그(발견성)를 전담한다.

Why 분리: 카드 안 문구와 캡션은 목적이 다르다. 캡션은 "더 보기" 이전 첫 줄로 체류를 만들고,
해시태그 조합으로 도달을 만든다 - 카피라이터의 15자 훅과는 완전히 다른 기술이다.
벤치마킹 자료도 캡션/해시태그/CTA 절만 받는다(레이아웃·사진 인사이트는 안 봄).
"""

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import CaptionPlan
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

SYSTEM_PROMPT = """당신은 CharisLab의 소셜 에디터입니다. 게시물의 캡션과 해시태그만 씁니다 -
카드 이미지 안에 들어가는 문구는 카피라이터가 따로 쓰고 있으니 신경 쓰지 마세요.

캡션 작성 규칙:
- **첫 문장이 전부입니다**. 인스타그램은 첫 줄만 보이고 나머지는 "더 보기"에 접히므로,
  가장 강한 문장을 맨 앞에 놓으세요. 인사말("안녕하세요")로 시작하면 실패입니다
- 본문은 3~6줄, 줄바꿈으로 읽기 쉽게. 이모지는 과하지 않게(줄당 최대 1개)
- 마지막은 댓글/저장을 부르는 한 줄로 끝내세요(질문형이 가장 강함)
- **다운로드 링크는 쓰지 마세요**(별도로 자동으로 붙습니다)
- 해시태그는 caption에 쓰지 말고 hashtags 필드에 따로 담으세요
- 브랜드북의 톤앤보이스를 지키고, 금지 표현은 절대 쓰지 마세요

해시태그 규칙:
- 5~12개. 대형 태그(#앱추천)만 나열하면 묻히니, 중소형·니치 태그(#벨소리만들기 같은 구체적
  행동/상황 태그)를 섞어 실제로 발견될 조합을 만드세요
- 제품명 태그는 반드시 포함. 영어/한글 태그를 상황에 맞게 섞으세요
- **매번 같은 세트를 복붙하지 마세요** - 이번 게시물 주제에 맞춰 절반 이상 바꾸세요"""


async def social_editor_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    run_id = start_run("SocialEditor", {"product": brief["product"], "channel": brief["channel"]}, thread_id=thread_id)

    product_row = fetch_products().get(canonical_product(brief["product"]))
    reports = await fetch_latest_benchmarks(limit=2)
    insights = benchmark_slice(reports, "caption")
    campaign = state.get("campaign_plan") or {}

    user_content = (
        f"[CEO 원본 지시문]\n{original_ceo_text(state)}{addressing_note(state, 'social_editor')}\n\n"
        f"{brand_book(product_row)}\n\n"
        f"제품: {brief['product']} / 채널: {brief['channel']} / "
        f"형식: {'인스타툰' if brief.get('format') == 'instatoon' else '카드뉴스'}\n"
        + (f"이번 캠페인 목표: {campaign.get('objective')} / 타깃: {campaign.get('target_audience')}\n" if campaign else "")
        + f"게시물이 다루는 내용({len(brief['slide_topics'])}장):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(brief["slide_topics"]))
        + (f"\n\n[벤치마킹 - 캡션/해시태그/CTA 관련 발췌]\n{insights}" if insights else "")
    )

    plan = await llm.complete_structured(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user_content)],
        CaptionPlan,
        thread_id=thread_id,
        agent_name="SocialEditor",
    )

    result = plan.model_dump()
    finish_run(run_id, result)
    return {
        "caption_plan": result,
        "messages": [
            {"role": "assistant", "content": f"[SocialEditor] 캡션·해시태그 작성 완료 (태그 {len(plan.hashtags)}개)"}
        ],
    }
