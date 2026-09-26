import logging

import httpx
from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import CreativeBrief, DirectorReview
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import (
    addressing_note,
    append_download_cta,
    benchmark_slice,
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
logger = logging.getLogger(__name__)

BRIEF_PROMPT = """당신은 CharisLab의 마케팅 디렉터입니다. CEO의 지시와 (있다면) 제품 특징 문서를
참고해서 홍보할 제품(product), 게시할 채널(channel: instagram|facebook|tiktok|threads), 콘텐츠
형식(format), 그리고 슬라이드/컷별 주제 목록(slide_topics)을 정하세요. 채널이 명시되지 않으면 지시
맥락상 가장 적합한 채널 하나를 고르세요.

**형식(format) 선택**: card_news(기존 카드뉴스)와 instatoon(마스코트 말풍선 만화) 중에서 상황과
벤치마킹 인사이트에 맞게 고르세요. 기능/스펙을 명확히 전달해야 하면 card_news, 짧고 공감 가는
에피소드로 자연스럽게 제품을 소개하고 싶으면(요즘 유행하는 형식) instatoon이 적합합니다. CEO가
형식을 직접 지정하지 않았다면 매번 같은 형식만 고르지 말고 적극적으로 섞어서 다양성을 확보하세요.

당신이 정한 slide_topics만 보고 네 명의 전문가가 서로의 결과물을 못 본 채 동시에 작업합니다 —
카피라이터(카드 안 문구), 소셜 에디터(캡션·해시태그), 포토 아트디렉터(사진 연출), 레이아웃
디자이너(카드 틀). 그러니 각 슬라이드/컷이 정확히 뭘 다루는지 구체적으로 적어야 네 사람의
결과물이 나중에 자연스럽게 맞아떨어집니다(예: "1번: '매일 반복되는 벨소리, 지겹지 않나요?' 식의
질문형 후킹" 처럼 톤/내용을 함께 지정).

**CEO 원문의 구체적 요청은 절대 누락하지 마세요(중요)**: CEO 지시에 색상/특정 요소/스타일/문구 등
구체적인 시각적·카피적 요청이 있으면(예: "배경은 파란색으로", "우리 로고 꼭 넣어줘", "이 스크린샷
써줘") 반드시 slide_topics 안에 그 요청을 명시적으로 적어서 담당 전문가에게 전달하세요 - 당신이
요약하는 과정에서 이런 구체적 요청이 사라지면 안 됩니다. 전문가들에게도 CEO 원문이 별도로
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

DIRECTOR_REVIEW_PROMPT = """당신은 CharisLab의 마케팅 디렉터입니다. 네 전문가(카피라이터, 소셜
에디터, 포토 아트디렉터, 레이아웃 디자이너)가 서로 못 본 채 만든 결과물이 하나의 게시물로
어울리는지 검토하세요. 소셜 에디터의 캡션이 카드 내용과 맞지 않거나 어색하면 다듬어
최종본(final_caption)으로 확정하고(해시태그는 그대로 두세요 - 뒤에 자동으로 붙습니다),
검토 소견(director_notes)을 1~2문장으로 남기세요(CEO가 승인 카드에서 보게 됩니다)."""


async def marketing_director_brief_node(state: OSState, config: RunnableConfig) -> dict:
    """마케팅 디렉터 1단계: 착수 전 크리에이티브 브리핑 작성. 이 브리핑만 보고 카피라이터/
    소셜 에디터/포토 아트디렉터가 병렬로(각자 다른 state 키에) 작업하고, 레이아웃 디자이너는
    포토 아트디렉터가 고른 스크린샷 자리를 알아야 해서 그 뒤에 이어 붙는다."""
    thread_id = config["configurable"]["thread_id"]
    run_id = start_run("MarketingDirector", {"ceo_directive": state["ceo_directive"]}, thread_id=thread_id)

    ceo_text = original_ceo_text(state)
    products_by_name = fetch_products()

    # 제품 컨텍스트는 앱관리(products 테이블)의 앱 설명을 그대로 쓴다 - 예전엔 RAG 문서 검색도
    # 섞었지만 문서가 3건뿐이라 기여가 없으면서 임베딩 API 장애로 마케팅 전체를 죽이는 원인이 됐다.
    product_descriptions = "\n".join(
        f"[{name} 앱 설명] {row['description']}" for name, row in products_by_name.items() if row.get("description")
    )
    context = product_descriptions or "(등록된 앱 설명 없음)"

    # 퍼포먼스 마케터가 입사해 있으면 그의 결정(제품/채널/타깃/각도)이 브리핑의 출발점이 된다.
    campaign = state.get("campaign_plan") or {}
    campaign_context = (
        "[퍼포먼스 마케터 결정 - 이 방향을 따르세요]\n"
        f"- 제품: {campaign.get('product')} / 채널: {campaign.get('channel')}\n"
        f"- 목표: {campaign.get('objective')}\n- 타깃: {campaign.get('target_audience')}\n"
        f"- 후킹 각도: {campaign.get('hook_angle')}\n- 근거: {campaign.get('rationale')}"
        if campaign
        else ""
    )

    reports = await fetch_latest_benchmarks(limit=2)
    insights = benchmark_slice(reports, "structure")

    user_content = (
        f"{ceo_text}{addressing_note(state, 'marketing_director')}\n\n{context}"
        + (f"\n\n{campaign_context}" if campaign_context else "")
        + (f"\n\n[벤치마킹 - 콘텐츠 구성 관련 발췌]\n{insights}" if insights else "")
    )

    creative_brief = await llm.complete_structured(
        [Message(role="system", content=BRIEF_PROMPT), Message(role="user", content=user_content)],
        CreativeBrief,
        thread_id=thread_id,
        agent_name="MarketingDirector",
    )

    # 장 수 상한: 프롬프트로 "3~5장"이라고 지시해도 7장을 만들어 오는 걸 실측으로 확인했다.
    # 장 하나당 이미지 1장(실제 비용)이라 코드로 자른다.
    brief_dict = creative_brief.model_dump()
    cap = 6 if brief_dict.get("format") == "instatoon" else 5
    if len(brief_dict["slide_topics"]) > cap:
        brief_dict["slide_topics"] = brief_dict["slide_topics"][:cap]

    finish_run(run_id, brief_dict)
    return {
        "creative_brief": brief_dict,
        "messages": [
            {
                "role": "assistant",
                "content": f"[MarketingDirector] 브리핑 작성 완료 - {brief_dict['product']}/{brief_dict['channel']}, "
                f"{brief_dict['format']} {len(brief_dict['slide_topics'])}장",
            }
        ],
    }


def _merge_specialist_plans(state: OSState) -> list[dict]:
    """네 전문가의 결과물을 장 번호로 맞춰 하나의 슬라이드 목록으로 합친다.

    각자 독립적으로 일해서 장 수가 어긋날 수 있으므로(예: 카피는 4장인데 사진은 3장) 가장 짧은
    쪽에 맞추지 않고 카피 기준으로 맞추고, 빠진 자리는 기본값으로 채운다 - 카드에 문구가 없는
    것보다 사진이 없는 게 낫다(사진 없는 레이아웃도 정상 렌더된다)."""
    copy_slides = (state.get("copy_plan") or {}).get("slides") or []
    photo_slides = (state.get("photo_plan") or {}).get("slides") or []
    layout_slides = (state.get("layout_plan") or {}).get("slides") or []

    # 전문가가 장 하나를 빠뜨려도 합성 단계가 죽지 않도록 기본값 위에 얹는다.
    default = {
        "headline": "",
        "subtext": "",
        "image_prompt": "",
        "real_screenshot_asset_id": None,
        "layout_name": "기본형",
        "layout_spec": {},
    }
    merged = []
    for i, copy_slide in enumerate(copy_slides):
        photo = photo_slides[i] if i < len(photo_slides) else {}
        layout = layout_slides[i] if i < len(layout_slides) else {}
        merged.append({**default, **copy_slide, **photo, **layout})
    return merged


def _force_device_for_screenshots(slide: dict) -> None:
    """실제 앱 스크린샷을 쓰는 장은 폰 목업 틀로 강제한다.

    Why 코드로 처리하는가: 레이아웃 디자이너가 포토 아트디렉터의 선택을 보려면 두 사람 사이에
    순서 의존이 생기고, 그러면 합성 노드가 두 번 실행되는 사고가 났다(build.py 주석 참고).
    "스크린샷이면 device" 는 판단이 아니라 규칙이므로 코드가 정한다 - 다른 틀로 두면 폰 화면이
    잘려서 무슨 화면인지 알아볼 수 없다(실측 확인).
    """
    if not slide.get("real_screenshot_asset_id"):
        return
    spec = dict(slide.get("layout_spec") or {})
    if spec.get("photo_style") != "device":
        spec["photo_style"] = "device"
        spec.setdefault("photo_area", "bottom")
        # 사진이 화면을 덮는 전제의 조합은 폰 목업과 맞지 않으므로 함께 정리한다.
        if spec.get("background") == "photo_full":
            spec["background"] = "brand_gradient"
        if spec.get("text_panel") == "scrim":
            spec["text_panel"] = "plain"
        if spec.get("text_position") == "bottom":
            spec["text_position"] = "top"
        slide["layout_spec"] = spec


def _ensure_photo_prompt(slide: dict, topic: str, product: str) -> None:
    """포토 아트디렉터가 image_prompt를 비워 보냈고 쓸 스크린샷도 없으면, 그 장의 내용으로
    사진 프롬프트를 채운다.

    Why: 실측에서 디렉터가 "카톡 대화창 스크린샷 목업"처럼 우리가 가지고 있지 않은 화면을
    요청하자 포토 아트디렉터가 모든 장의 image_prompt를 빈 문자열로 내보냈고, 결과적으로
    사진이 전혀 없는 카드가 만들어졌다. 프롬프트로도 막았지만(photo_art_director.py) 마지막
    안전망을 코드에 둔다 - 사진 없는 카드가 CEO 결재까지 올라가는 것보다는 낫다."""
    if slide.get("image_prompt") or slide.get("real_screenshot_asset_id"):
        return
    subject = slide.get("headline") or topic
    slide["image_prompt"] = (
        f"Candid photo of Korean people in a realistic everyday situation that shows: {subject}. "
        f"Related to a mobile app ({product}). Natural bright daylight, neutral white balance, "
        "wide shot with headroom above the head, no text or logos in the image."
    )


def _reusable_source(state: OSState, index: int, slide: dict) -> str | None:
    """이전 회차에서 쓴 원본 사진을 그대로 재사용해도 되는지 판단해 그 URL을 돌려준다.

    Why: 보완(revision)에서 문구나 틀만 바뀐 경우에도 예전엔 사진을 전부 새로 생성했다 -
    한 번에 이미지 3~5장 비용이 그대로 다시 나갔다. 사진 지시문과 스크린샷 선택이 이전과
    같다면 사진이 달라질 이유가 없으므로 보관해둔 원본을 재사용한다(이미지 비용 0)."""
    previous = (state.get("marketing_post") or {}).get("slides") or []
    if index >= len(previous):
        return None
    before = previous[index]
    same_prompt = (before.get("image_prompt") or "") == (slide.get("image_prompt") or "")
    same_asset = before.get("real_screenshot_asset_id") == slide.get("real_screenshot_asset_id")
    return before.get("source_image_url") if same_prompt and same_asset else None


async def marketing_synthesis_node(state: OSState, config: RunnableConfig) -> dict:
    """마케팅 디렉터 2단계: 네 전문가의 결과물이 모두 도착한 뒤(LangGraph join) 슬라이드를
    합치고, 사진을 만들고, 카드를 합성해 marketing_post를 완성한다."""
    thread_id = config["configurable"]["thread_id"]
    brief = state["creative_brief"]
    caption_plan = state.get("caption_plan") or {}

    run_id = start_run(
        "MarketingDirector",
        {"product": brief["product"], "channel": brief["channel"]},
        thread_id=thread_id,
    )

    merged_slides = _merge_specialist_plans(state)
    for i, slide in enumerate(merged_slides):
        topic = brief["slide_topics"][i] if i < len(brief["slide_topics"]) else ""
        _ensure_photo_prompt(slide, topic, brief["product"])
        _force_device_for_screenshots(slide)

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
                slide.get("image_prompt", ""),
                slide.get("headline", ""),
                slide.get("subtext", ""),
                brief["product"],
                page_label=f"{i + 1}/{total}",
                brand_color=brand_color,
                thread_id=thread_id,
                agent_name="PhotoArtDirector",
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

                reuse_url = _reusable_source(state, i, slide)
                reused = False
                if reuse_url:
                    resp = await client.get(reuse_url)
                    if resp.status_code == 200:
                        kwargs["illustration_bytes"] = resp.content
                        reused = True

                if "illustration_bytes" not in kwargs:
                    asset = assets_by_id.get(slide.get("real_screenshot_asset_id") or "")
                    if asset:
                        public_url = (
                            get_supabase().storage.from_("product-assets").get_public_url(asset["storage_path"])
                        )
                        resp = await client.get(public_url)
                        if resp.status_code == 200:
                            kwargs["illustration_bytes"] = resp.content

                card_bytes, source_bytes = await compose_marketing_card(
                    slide.get("image_prompt", ""),
                    slide.get("headline", ""),
                    slide.get("subtext", ""),
                    brief["product"],
                    thread_id=thread_id,
                    agent_name="PhotoArtDirector",
                    return_source=True,
                    **kwargs,
                )
                # 원본 사진도 보관한다 - 편집기에서 문구/틀만 바꿔 다시 그릴 때 AI 재생성 없이
                # 이 사진을 그대로 재사용하기 위함(수정 비용 0). 이전 회차 사진을 그대로 쓴
                # 경우에는 같은 파일을 또 올리지 않고 기존 URL을 유지한다(스토리지 중복 방지).
                slide["source_image_url"] = reuse_url if reused else upload_marketing_image(source_bytes)
                image_urls.append(upload_marketing_image(card_bytes))

    review = await llm.complete_structured(
        [
            Message(role="system", content=DIRECTOR_REVIEW_PROMPT),
            Message(
                role="user",
                content=f"캡션: {caption_plan.get('caption', '')}\n슬라이드: {merged_slides}",
            ),
        ],
        DirectorReview,
        thread_id=thread_id,
        agent_name="MarketingDirector",
    )

    caption = append_download_cta(review.final_caption, brief["product"], brief["channel"], products_by_name)
    hashtags = caption_plan.get("hashtags") or []
    if hashtags:
        caption = f"{caption}\n\n{' '.join(hashtags)}"

    # 쇼츠/릴스 - 이미 만든 이미지를 재활용하는 것이라 AI 비용이 0이다. 렌더링(CPU)만 하면
    # 노출 채널이 하나 더 생긴다. 실패해도 게시물 자체는 유효하므로 조용히 건너뛴다.
    video_url = None
    try:
        from app.services.shorts import render_from_images, upload_video

        video_url = upload_video(
            render_from_images(image_urls, brief["product"], brand=brand_color)
        )
    except Exception:
        logger.exception("쇼츠 생성 실패 - 게시물은 그대로 진행")

    marketing_post = {
        "product": brief["product"],
        "channel": brief["channel"],
        "format": brief.get("format", "card_news"),
        "caption": caption,
        "slides": merged_slides,
        "image_urls": image_urls,
        "video_url": video_url,  # 쇼츠/릴스 - 없을 수도 있음(렌더 실패 시)
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
