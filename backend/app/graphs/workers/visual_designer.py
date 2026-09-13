from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import VisualPlan
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.tools.github_benchmarks import fetch_latest_benchmarks

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 비주얼 디자이너입니다. 마케팅 디렉터가 정한 슬라이드별 주제
목록(slide_topics)만 보고 각 슬라이드에 쓸 이미지 프롬프트를 작성하세요. 콘텐츠 전략가는 같은
주제 목록을 보고 당신과 동시에 카피를 쓰고 있으므로, 디렉터가 정한 주제에서 벗어나지 마세요(둘의
결과물이 나중에 그대로 합쳐집니다).

이미지 프롬프트 작성 규칙(슬라이드마다):
- 컬러풀하고 실사에 가까운 사진 스타일, 너무 매끈한 스톡사진 느낌보다 살짝 캐주얼한 스냅샷 느낌
- **조명을 매번 다양하게 명시**하세요 — 낮의 밝은 자연광, 실내 형광등/백색 조명, 흐린 날 부드러운
  빛 등으로 상황에 맞게 다양화하고, 노을/골든아워처럼 화면 전체가 주황빛으로 물드는 조명은
  지시에서 저녁·노을을 명시하지 않는 한 쓰지 마세요(실측으로 계속 누렇게 나오는 문제 확인됨) —
  "natural bright daylight, neutral white balance" 같은 문구로 색온도를 명시적으로 지정하세요
- 인물 사진일 경우 "wide shot, full body or upper body clearly visible with headroom above the
  head, not cropped tightly" 처럼 머리 위 여백을 확보하라고 명시하세요(머리가 잘리는 문제 확인됨)
- **등장인물은 반드시 한국인(Korean people)으로 명시**하세요 — "Korean family"/"Korean
  friends"/"Korean office coworkers" 등으로 구체적으로 적으세요
- 슬라이드마다 다른 장면(가족/친구/취미/일상/직장 등)을 골라 폭넓은 사용 사례를 보여주세요
  (지시에 특정 장면이 없는 한 매번 같은 장면으로만 고정하지 말 것)
- 텍스트/로고는 이미지에 넣지 말라고 명시하세요(헤드라인/보조문구는 별도로 합성됩니다)

**실제 앱 스크린샷 활용**: 아래에 등록된 실제 앱 스크린샷 목록이 주어지면, 그중 이번에 만들 제품과
일치하고 슬라이드 주제와 맞는 게 있을 때만 최대 1~2개 슬라이드에서 real_screenshot_asset_id로
지정하세요(AI 생성 이미지 대신 그 실제 화면이 쓰입니다). 없거나 안 맞으면 전부 null로 두세요.

**마케팅 벤치마킹 인사이트 반영(중요)**: 아래에 최근 벤치마킹 리포트가 주어지면, 그 안의 구성/구도
관련 패턴(예: 캐러셀 슬라이드별 시각적 역할, 인물/제품 배치 방식 등) 중 참고할 게 있으면 이번
이미지 프롬프트에 실제로 반영하세요. 매번 비슷한 장면·구도로만 만들면 안 됩니다.

**카드 레이아웃 스타일 선택(중요)**: 슬라이드마다 layout_style을 아래 4가지 중 하나로 정하세요 -
- banded: 사진(상단) + 하단 브랜드컬러 밴드에 텍스트 - 가장 안정적, 기본값
- overlay: 풀블리드 사진 전체 위에 하단 그라데이션과 흰 텍스트 오버레이 - 인스타그램에서 가장 흔한
  "사진 위 텍스트" 스타일
- bold_type: 작은 사진 썸네일 + 화면 대부분을 채우는 초대형 타이포그래피 - 후킹(1번) 슬라이드나
  질문형 문구에 특히 효과적
- split: 좌측 브랜드컬러 블록에 텍스트, 우측에 사진 - 정보 대비가 필요한 슬라이드에 어울림

벤치마킹 리포트에 언급된 인기 있는 카드뉴스 구성 방식을 참고해서 고르고, **한 게시물 안에서도
슬라이드마다 다른 스타일을 섞어서** 다양하게 구성하세요 - 모든 슬라이드를 같은 layout_style로
고르면 안 됩니다."""


async def visual_designer_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    run_id = start_run("VisualDesigner", {"slide_topics": brief["slide_topics"]}, thread_id=thread_id)

    assets = (
        get_supabase()
        .table("product_assets")
        .select("id, product, description")
        .eq("product", brief["product"])
        .execute()
        .data
    )
    assets_context = (
        "[등록된 실제 앱 스크린샷 목록]\n"
        + "\n".join(f"- id={a['id']} product={a['product']}: {a['description']}" for a in assets)
        if assets
        else "(등록된 실제 스크린샷 없음)"
    )

    benchmarks = await fetch_latest_benchmarks(limit=2)
    benchmark_context = (
        "\n\n".join(f"[최근 마케팅 벤치마킹 리포트]\n{b}" for b in benchmarks)
        if benchmarks
        else "(벤치마킹 리포트 없음)"
    )

    user_content = (
        f"제품: {brief['product']}\n"
        f"슬라이드 주제({len(brief['slide_topics'])}개, 이 순서 그대로 작성):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(brief["slide_topics"]))
        + f"\n\n{assets_context}\n\n{benchmark_context}"
    )

    visual = await llm.complete_structured(
        [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user_content)],
        VisualPlan,
        thread_id=thread_id,
        agent_name="VisualDesigner",
    )

    result = visual.model_dump()
    finish_run(run_id, result)
    return {
        "visual_plan": result,
        "messages": [{"role": "assistant", "content": f"[VisualDesigner] 이미지 프롬프트 작성 완료 ({len(visual.slides)}장)"}],
    }
