"""포토 아트디렉터 - 각 장의 "사진"만 책임진다(장면·조명·인물·구도 + 실제 스크린샷 선택).

Why 분리: 예전 "비주얼 디자이너" 한 명이 ①사진 연출 ②카드 틀 설계 ③스크린샷 선택을 전부
겸했고, 그 결과 시스템 프롬프트가 1,500토큰을 넘겨 뒤쪽 지침을 흘리기 시작했다(실측 사고:
"mp3가 안 열려 답답한 장면"에 정원에서 수채화 그리는 할머니 사진이 나옴). 사진 연출과 조판은
평가 기준이 다른 일이라 사람을 나눈다 - 이 사람은 "사진이 그 장의 내용을 보여주는가"만 본다.
인스타툰일 때는 같은 자리에서 컷 연출(포즈·표정·배경)을 맡는다.
"""

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import PhotoPlan
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

SYSTEM_PROMPT_CARD_NEWS = """당신은 CharisLab의 포토 아트디렉터입니다. 카드뉴스 각 장에 쓸
"사진"만 책임집니다 - 카드 틀/타이포는 레이아웃 디자이너가, 문구는 카피라이터가 따로 맡고
있으니 신경 쓰지 마세요. 장별 주제(slide_topics)와 같은 개수·순서로 image_prompt를 쓰세요.

**가장 중요 - 사진은 그 장이 말하는 내용을 직접 보여줘야 합니다.** 주제와 상관없는 "분위기용
사진"은 절대 안 됩니다(실측 사고: "카톡으로 받은 mp3가 아이튠즈 없이 안 열린다"는 장에 정원에서
수채화 그리는 할머니 사진이 나와 아무도 무슨 말인지 몰랐음). 그 장의 불편함/해결 장면을 사람의
행동과 표정으로 구체적으로 그리세요. 예: "mp3가 안 열려 답답함" → "폰 화면을 보며 미간을
찌푸린 한국인 20~30대, 화면엔 오류 안내가 떠 있는 느낌".

연출 규칙:
- 컬러풀하고 실사에 가까운 사진, 매끈한 스톡사진보다 살짝 캐주얼한 스냅샷 느낌
- **등장인물은 반드시 한국인으로 명시**("Korean family", "Korean office coworkers" 등)
- 인물 사진은 "wide shot, full body or upper body clearly visible with headroom above the head,
  not cropped tightly"처럼 머리 위 여백을 명시(머리 잘림 문제 실측 확인)
- **조명을 매 장 다르게 명시**하고, 노을/골든아워는 지시에 저녁·노을이 명시된 경우에만 쓰세요
  (화면이 계속 누렇게 나오는 문제 실측 확인) - "natural bright daylight, neutral white balance"
  처럼 색온도를 분명히 적으세요
- 텍스트/로고는 이미지에 넣지 말라고 명시(문구는 나중에 따로 합성됩니다)
- 다양성보다 "내용과 맞는가"가 우선 - 장면을 억지로 다양화하려고 주제에서 벗어나지 마세요

**실제 앱 스크린샷**: 아래 목록에 이번 제품 화면이 있고 그 장의 주제와 맞으면, 최대 1~2개 장에만
real_screenshot_asset_id를 지정하세요(그 장은 AI 사진 대신 실제 화면이 쓰입니다). 목록에 없는
화면(카톡 대화창, 다른 앱 화면 등)은 우리가 가진 자산이 아니므로 절대 지정하지 마세요.

**모든 장에 image_prompt를 반드시 쓰세요(가장 흔한 사고)**: real_screenshot_asset_id를 실제로
지정한 장에서만 image_prompt를 비울 수 있습니다. 나머지 장을 비우면 그 장은 사진 없이 나갑니다.
디렉터가 "○○ 스크린샷 목업"처럼 우리가 가지고 있지 않은 화면을 요청했더라도, 그 장면을 사람의
행동으로 재현하는 사진 프롬프트를 직접 쓰세요(예: 카톡 대화창이 필요하면 "한국인 20대가 메신저로
받은 음악 파일을 보고 있는 폰 화면, 손에 든 폰 클로즈업").

**CEO 원문 확인**: 색상/특정 요소/스타일 등 사진에 관한 구체적 요청이 있으면 반드시 반영하세요."""

SYSTEM_PROMPT_INSTATOON = """당신은 CharisLab의 포토 아트디렉터이자 이번 인스타툰의 컷 연출을
맡습니다. 마스코트 캐릭터가 등장하는 말풍선 만화의 "각 컷 장면"을 image_prompt에 영어로 쓰세요
(대사는 카피라이터가 따로 씁니다). 컷별 주제와 같은 개수·순서로 작성하세요.

**캐릭터 외형은 절대 다시 묘사하지 마세요**: 마스코트 외형은 고정된 참조 이미지로 정해져 있고
그 이미지를 기반으로 이번 컷을 그립니다. image_prompt에는 **이 컷에서 캐릭터가 무엇을 하는지
(포즈/표정/행동)와 배경/상황만** 쓰세요. 예: "the character looking surprised while holding a
phone, sitting on a sofa at home, warm indoor lighting" ("a cute blue creature" 같은 외형 묘사 금지).

- 표정/감정을 분명하게(놀람, 답답함, 만족감) 그려 대사 없이도 상황이 읽히게
- 배경은 실제 사용 맥락(집, 카페, 지하철, 침대 등)을 구체적으로
- **매 컷 image_prompt 끝에 다음 문구를 그대로 붙이세요**: "Korean webtoon style, simple line art,
  flat colors, clean bold outlines, minimal shading, no photorealistic rendering, no glossy 3D
  render" — 컷마다 그림체가 흔들리면 인스타툰으로 안 보입니다
- 브랜드 컬러가 주어지면 배경 소품 하나 정도에만 은근하게 반영(1~2컷, 과하게 넣지 말 것)
- 텍스트/말풍선/로고는 이미지에 넣지 말라고 명시(말풍선은 따로 합성됩니다)
- real_screenshot_asset_id는 항상 null(마스코트 만화라 앱 스크린샷을 쓰지 않습니다)"""


async def photo_art_director_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    is_instatoon = brief.get("format") == "instatoon"
    system_prompt = SYSTEM_PROMPT_INSTATOON if is_instatoon else SYSTEM_PROMPT_CARD_NEWS
    run_id = start_run("PhotoArtDirector", {"slide_topics": brief["slide_topics"]}, thread_id=thread_id)

    product_row = fetch_products().get(canonical_product(brief["product"]))
    if is_instatoon:
        brand_hex = (product_row or {}).get("brand_color")
        assets_context = "(인스타툰 - 실제 스크린샷 미사용)" + (
            f"\n브랜드 컬러: {brand_hex} (배경 소품에만 은근하게)" if brand_hex else ""
        )
    else:
        assets = (
            get_supabase()
            .table("product_assets")
            .select("id, product, description")
            .eq("product", brief["product"])
            .execute()
            .data
        )
        assets_context = (
            "[등록된 실제 앱 스크린샷]\n"
            + "\n".join(f"- id={a['id']}: {a['description']}" for a in assets)
            if assets
            else "(등록된 실제 스크린샷 없음)"
        )

    reports = await fetch_latest_benchmarks(limit=2)
    insights = benchmark_slice(reports, "photo")

    user_content = (
        f"[CEO 원본 지시문]\n{original_ceo_text(state)}{addressing_note(state, 'photo_art_director')}\n\n"
        f"{brand_book(product_row)}\n\n"
        f"제품: {brief['product']}\n"
        f"{'컷' if is_instatoon else '슬라이드'} 주제({len(brief['slide_topics'])}개, 이 순서 그대로):\n"
        + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(brief["slide_topics"]))
        + f"\n\n{assets_context}"
        + (f"\n\n[벤치마킹 - 사진/장면 관련 발췌]\n{insights}" if insights else "")
    )

    plan = await llm.complete_structured(
        [Message(role="system", content=system_prompt), Message(role="user", content=user_content)],
        PhotoPlan,
        thread_id=thread_id,
        agent_name="PhotoArtDirector",
    )

    result = plan.model_dump()
    finish_run(run_id, result)
    return {
        "photo_plan": result,
        "messages": [
            {"role": "assistant", "content": f"[PhotoArtDirector] 사진 연출 완료 ({len(plan.slides)}장)"}
        ],
    }
