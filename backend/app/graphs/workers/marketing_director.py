import httpx
from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import CreativeBrief, DirectorReview
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import (
    append_download_cta,
    canonical_product,
    fetch_products,
    hex_to_rgb,
    original_ceo_text,
)
from app.tools.ai.image.card_composer import compose_instatoon_panel, compose_marketing_card
from app.tools.ai.image.card_renderer import DEFAULT_BRAND
from app.tools.ai.image.mascot import ensure_mascot
from app.tools.ai.image.storage import upload_marketing_image
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.tools.github_benchmarks import fetch_latest_benchmarks

llm = get_llm()

BRIEF_PROMPT = """당신은 CharisLab의 마케팅 디렉터입니다. CEO의 지시와 (있다면) 제품 특징 문서를
참고해서 홍보할 제품(product), 게시할 채널(channel: instagram|facebook|tiktok|threads), 콘텐츠
형식(format), 그리고 슬라이드/컷별 주제 목록(slide_topics)을 정하세요. 채널이 명시되지 않으면 지시
맥락상 가장 적합한 채널 하나를 고르세요.

**형식(format) 선택**: card_news(기존 카드뉴스)와 instatoon(마스코트 말풍선 만화) 중에서 상황과
벤치마킹 인사이트에 맞게 고르세요. 기능/스펙을 명확히 전달해야 하면 card_news, 짧고 공감 가는
에피소드로 자연스럽게 제품을 소개하고 싶으면(요즘 유행하는 형식) instatoon이 적합합니다. CEO가
형식을 직접 지정하지 않았다면 매번 같은 형식만 고르지 말고 적극적으로 섞어서 다양성을 확보하세요.

당신이 정한 slide_topics만 보고 콘텐츠 전략가(카피/대화 담당)와 비주얼 디자이너(이미지 담당)가
서로의 결과물을 못 본 채 동시에 작업합니다 — 그러니 각 슬라이드/컷이 정확히 뭘 다루는지 구체적으로
적어야 두 사람의 결과물이 나중에 자연스럽게 맞아떨어집니다(예: "1번: '매일 반복되는 벨소리, 지겹지
않나요?' 식의 질문형 후킹" 처럼 톤/내용을 함께 지정).

**CEO 원문의 구체적 요청은 절대 누락하지 마세요(중요)**: CEO 지시에 색상/특정 요소/스타일/문구 등
구체적인 시각적·카피적 요청이 있으면(예: "배경은 파란색으로", "우리 로고 꼭 넣어줘", "이 스크린샷
써줘") 반드시 slide_topics 안에 그 요청을 명시적으로 적어서 전략가/디자이너에게 전달하세요 - 당신이
요약하는 과정에서 이런 구체적 요청이 사라지면 안 됩니다. 전략가/디자이너에게도 CEO 원문이 별도로
전달되지만, slide_topics에서부터 명확히 짚어주는 게 훨씬 안전합니다.

슬라이드/컷 구성: card_news는 3~5개(1번은 후킹, 중간은 기능/베네핏을 하나씩, 마지막은 CTA).
instatoon은 4~6개, 기승전결 구조로: 기(1컷, 상황 설정) → 승(1~2컷, 공감되는 불편/갈등이
과장되게 심화됨 - 페인포인트를 코믹하게 부각) → 전(1~2컷, 제품으로 자연스럽게 해결되는 반전) →
결(1컷, 만족스러운 마무리 + 댓글/공유를 유도하는 질문형 대사로 종료 - 다운로드 CTA는 캡션에 별도로
자동으로 붙으니 컷 안에 억지로 넣지 말 것).

**마케팅 벤치마킹 인사이트 반영(중요)**: 아래에 최근 벤치마킹 리포트가 주어지면, 그 안의 구체적인
패턴(후킹 방식, 슬라이드 구성, 캡션 톤, CTA 문구 스타일, 인스타툰 에피소드 소재/컷 구성 등) 중
최소 1~2가지를 이번 구성에 실제로 적용하세요. 매번 비슷한 구성으로만 만들면 안 됩니다 — 지난 번과는
확실히 다른 후킹 방식/구성을 시도하세요."""

DIRECTOR_REVIEW_PROMPT = """당신은 CharisLab의 마케팅 디렉터입니다. 콘텐츠 전략가가 쓴 캡션과
비주얼 디자이너가 준비한 슬라이드 구성이 서로 잘 어울리는지 검토하세요. 캡션이 슬라이드 내용과
맞지 않거나 어색하면 다듬어서 최종본(final_caption)으로 확정하고, 검토 소견(director_notes)을
1~2문장으로 남기세요(CEO가 승인 카드에서 보게 됩니다)."""


def _gather_context(state: OSState) -> tuple[str, dict[str, dict]]:
    """브리핑 작성에 필요한 지시문 + 참고 컨텍스트를 모은다."""
    return original_ceo_text(state), fetch_products()


async def marketing_director_brief_node(state: OSState, config: RunnableConfig) -> dict:
    """마케팅 디렉터 1단계: 착수 전 크리에이티브 브리핑 작성. 이 결과만 보고 콘텐츠 전략가와
    비주얼 디자이너가 병렬로(각자 다른 state 키에) 작업한다."""
    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("MarketingDirector", {"ceo_directive": state["ceo_directive"]}, thread_id=thread_id)

    brief, products_by_name = _gather_context(state)

    # 제품 컨텍스트는 앱관리(products 테이블)의 앱 설명을 그대로 쓴다 - 예전엔 RAG 문서 검색도
    # 섞었지만 문서가 3건뿐이라 기여가 없으면서 임베딩 API 장애로 마케팅 전체를 죽이는 원인이 됐다.
    product_descriptions = "\n".join(
        f"[{name} 앱 설명] {row['description']}" for name, row in products_by_name.items() if row.get("description")
    )
    context = product_descriptions or "(등록된 앱 설명 없음)"

    benchmarks = await fetch_latest_benchmarks(limit=2)
    benchmark_context = (
        "\n\n".join(f"[최근 마케팅 벤치마킹 리포트]\n{b}" for b in benchmarks)
        if benchmarks
        else "(벤치마킹 리포트 없음)"
    )

    creative_brief = await llm.complete_structured(
        [
            Message(role="system", content=BRIEF_PROMPT),
            Message(role="user", content=f"{brief}\n\n{context}\n\n{benchmark_context}"),
        ],
        CreativeBrief,
        thread_id=thread_id,
        agent_name="MarketingDirector",
    )

    finish_run(run_id, creative_brief.model_dump())
    return {
        "creative_brief": creative_brief.model_dump(),
        "messages": [
            {
                "role": "assistant",
                "content": f"[MarketingDirector] 브리핑 작성 완료 - {creative_brief.product}/{creative_brief.channel}, 슬라이드 {len(creative_brief.slide_topics)}개",
            }
        ],
    }


async def marketing_synthesis_node(state: OSState, config: RunnableConfig) -> dict:
    """마케팅 디렉터 2단계: ContentStrategist·VisualDesigner가 둘 다 끝난 뒤(LangGraph join)
    슬라이드를 합치고, 실제 이미지를 합성하고, 최종 검토해서 marketing_post를 완성한다."""
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    content = state["content_strategy"]
    visual = state["visual_plan"]

    run_id = start_run(
        "MarketingDirector",
        {"product": brief["product"], "channel": brief["channel"]},
        thread_id=thread_id,
    )

    merged_slides = [{**c, **v} for c, v in zip(content["slides"], visual["slides"])]

    products_by_name = fetch_products()
    assets = get_supabase().table("product_assets").select("id, storage_path").execute().data
    assets_by_id = {a["id"]: a for a in assets}

    product_row = products_by_name.get(canonical_product(brief["product"])) or {}
    brand_color = hex_to_rgb(product_row.get("brand_color")) or DEFAULT_BRAND
    total = len(merged_slides)
    image_urls = []

    if brief.get("format") == "instatoon":
        # 인스타툰: 마스코트 참조 이미지를 한 번만 준비하고, 모든 컷에서 재사용해 캐릭터 외형을
        # 최대한 일관되게 유지한다(마스코트 캐릭터라 실제 스크린샷/AI 사진 생성 경로는 안 씀).
        mascot_bytes = await ensure_mascot(product_row or {"name": brief["product"]})
        for i, slide in enumerate(merged_slides):
            panel_bytes, panel_source = await compose_instatoon_panel(
                mascot_bytes,
                slide["image_prompt"],
                slide["headline"],
                slide.get("subtext", ""),
                brief["product"],
                page_label=f"{i + 1}/{total}",
                brand_color=brand_color,
                thread_id=thread_id,
                agent_name="VisualDesigner",
                return_source=True,
            )
            # 말풍선을 얹기 전 컷 그림도 보관한다 - 편집기에서 대사만 고쳐 다시 얹을 때
            # AI 재생성 없이 이 그림을 그대로 쓴다(카드뉴스의 source_image_url과 같은 목적).
            slide["source_image_url"] = upload_marketing_image(panel_source)
            image_urls.append(upload_marketing_image(panel_bytes))
    else:
        async with httpx.AsyncClient(timeout=30) as client:
            for i, slide in enumerate(merged_slides):
                kwargs = {
                    "page_label": f"{i + 1}/{total}",
                    "layout_spec": slide.get("layout_spec"),
                    "brand_color": brand_color,
                }

                asset = assets_by_id.get(slide.get("real_screenshot_asset_id") or "")
                if asset:
                    public_url = get_supabase().storage.from_("product-assets").get_public_url(asset["storage_path"])
                    resp = await client.get(public_url)
                    if resp.status_code == 200:
                        kwargs["illustration_bytes"] = resp.content

                card_bytes, source_bytes = await compose_marketing_card(
                    slide["image_prompt"],
                    slide["headline"],
                    slide["subtext"],
                    brief["product"],
                    thread_id=thread_id,
                    agent_name="VisualDesigner",
                    return_source=True,
                    **kwargs,
                )
                # 원본 사진도 보관한다 - 편집기에서 문구/틀만 바꿔 다시 그릴 때 AI 재생성 없이
                # 이 사진을 그대로 재사용하기 위함(수정 비용 0).
                slide["source_image_url"] = upload_marketing_image(source_bytes)
                image_urls.append(upload_marketing_image(card_bytes))

    review = await llm.complete_structured(
        [
            Message(role="system", content=DIRECTOR_REVIEW_PROMPT),
            Message(
                role="user",
                content=f"캡션: {content['caption']}\n슬라이드: {merged_slides}",
            ),
        ],
        DirectorReview,
        thread_id=thread_id,
        agent_name="MarketingDirector",
    )

    caption = append_download_cta(review.final_caption, brief["product"], brief["channel"], products_by_name)

    marketing_post = {
        "product": brief["product"],
        "channel": brief["channel"],
        "format": brief.get("format", "card_news"),
        "caption": caption,
        "slides": merged_slides,
        "image_urls": image_urls,
        "director_notes": review.director_notes,
    }
    finish_run(run_id, marketing_post)
    return {
        "marketing_post": marketing_post,
        "messages": [
            {
                "role": "assistant",
                "content": f"[MarketingDirector] 최종 검토 완료 - {brief['product']}/{brief['channel']} ({total}장)",
            }
        ],
    }
