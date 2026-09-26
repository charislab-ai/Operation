"""레이아웃 디자이너 - 장마다 어떤 카드 틀로 조판할지만 정한다.

Why 분리: "매번 같은 카드 틀로만 나온다"는 CEO 지적의 전담자가 없었다. 사진 연출과 조판을
한 사람이 겸하면(예전 비주얼 디자이너) 사진 지침에 밀려 틀 설계가 뒤로 밀린다. 이 사람은
틀 라이브러리(벤치마킹이 찾아낸 실제 인기 틀)를 자기 자산으로 들고, 장별 역할에 맞춰 고르거나
조합하는 일만 한다. 인스타툰은 만화 컷이라 조판 개념이 없어 이 노드는 빈 결과를 돌려준다.
"""

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import LayoutPlan
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

SYSTEM_PROMPT = """당신은 CharisLab의 레이아웃 디자이너입니다. 카드뉴스 각 장을 "어떤 틀로
조판할지"만 정합니다 - 사진 연출은 포토 아트디렉터가, 문구는 카피라이터가 맡고 있습니다.
장별 주제(slide_topics)와 같은 개수·순서로 layout_name과 layout_spec을 쓰세요.

아래 "틀 라이브러리"는 하루 2회 도는 벤치마킹이 실제 인스타그램에서 찾아내 기억해둔 인기
틀들이고, 각 틀에 "언제 쓰면 좋은지"가 적혀 있습니다.

1. 이 장이 하려는 말에 **가장 잘 맞는 틀을 라이브러리에서 고르세요** - 이름을 layout_name에,
   spec을 layout_spec에 그대로 넣습니다.
2. 딱 맞는 게 없으면 **여러 틀의 요소를 조합해 새 틀을 만드세요** - 배경/사진처리/사진위치/
   기울기/텍스트패널/텍스트위치/제목크기/강조를 직접 정하고 새 이름을 지으세요
   (예: "폴라로이드+체크리스트형"). 벤치마킹에서 본 틀을 조합으로 재현해도 좋습니다.
3. **한 게시물 안에서 같은 틀을 반복하지 마세요.** 장마다 역할이 다르니 틀도 달라야 합니다
   (1장=시선을 잡는 강한 틀, 중간=정보 전달, 마지막=행동 유도).
4. 포토 아트디렉터가 실제 앱 스크린샷을 쓰기로 한 장은 합성 단계에서 자동으로 폰 목업
   (photo_style="device")으로 바뀝니다 - 당신은 신경 쓰지 말고 내용에 맞는 틀을 고르세요.
5. 글자 수를 고려하세요 - 제목이 길면 headline_scale을 "xl"로 두지 마세요(잘립니다). 사진 위에
   글자를 얹을 땐(background=photo_full) text_panel을 scrim이나 white_card로 해서 대비를
   확보하세요. 밝은 배경(light/paper)에 흰 글자를 올리는 조합은 절대 만들지 마세요.
6. 브랜드북의 톤과 어울리는 조합을 고르세요(차분한 브랜드에 형광펜 강조를 남발하지 말 것)."""


async def layout_designer_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    topics = brief["slide_topics"]

    if brief.get("format") == "instatoon":
        # 인스타툰은 말풍선 만화라 조판할 틀이 없다 - 레이아웃 디자이너는 이번 건에 투입되지
        # 않는다(빈 결과를 돌려 합성 단계가 기본값을 쓰게 함).
        return {
            "layout_plan": {"slides": []},
            "messages": [{"role": "assistant", "content": "[LayoutDesigner] 인스타툰 - 조판 불필요, 미투입"}],
        }

    run_id = start_run("LayoutDesigner", {"slide_topics": topics}, thread_id=thread_id)
    product_row = fetch_products().get(canonical_product(brief["product"]))

    layouts = (
        get_supabase()
        .table("layout_library")
        .select("name, when_to_use, spec")
        .eq("enabled", True)
        .order("name")
        .execute()
        .data
    )
    layout_context = (
        "[틀 라이브러리 - 벤치마킹으로 찾아낸 카드 틀]\n"
        + "\n".join(f"- {l['name']}: {l['when_to_use']}\n  spec={l['spec']}" for l in layouts)
        if layouts
        else "(틀 라이브러리가 비어있음 - 직접 조합해 설계할 것)"
    )

    reports = await fetch_latest_benchmarks(limit=2)
    insights = benchmark_slice(reports, "layout")

    user_content = (
        f"[CEO 원본 지시문]\n{original_ceo_text(state)}{addressing_note(state, 'layout_designer')}\n\n"
        f"{brand_book(product_row)}\n\n"
        f"제품: {brief['product']}\n"
        f"슬라이드 주제({len(topics)}개, 이 순서 그대로):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(topics))
        + f"\n\n{layout_context}"
        + (f"\n\n[벤치마킹 - 레이아웃/디자인 관련 발췌]\n{insights}" if insights else "")
    )

    plan = await llm.complete_structured(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user_content)],
        LayoutPlan,
        thread_id=thread_id,
        agent_name="LayoutDesigner",
    )

    result = plan.model_dump()
    finish_run(run_id, result)
    return {
        "layout_plan": result,
        "messages": [
            {
                "role": "assistant",
                "content": f"[LayoutDesigner] 조판 완료 - {', '.join(s['layout_name'] for s in result['slides'])}",
            }
        ],
    }
