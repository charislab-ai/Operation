"""브랜드 QA - 완성된 카드 이미지를 실제로 "보고" 검수한다.

Why 신설: 지금까지 렌더링된 최종 이미지를 눈으로 확인하는 담당자가 아무도 없었다. 디렉터의
최종 검토는 캡션 텍스트만 봤고, 글자 잘림·대비 부족·브랜드 톤 위반은 전부 CEO가 결재 화면에서
직접 발견해야 했다(실측: 어두운 배경에서 제품 뱃지가 안 보이던 문제, 마커 강조가 글자를 덮던
문제 모두 CEO 지적으로 발견됨).

동작: 카드 이미지를 멀티모달 LLM에 그대로 넘겨 판정을 받고, 자동 교정이 가능한 문제
(제목 너무 김/대비 부족/위치 충돌)는 **AI 이미지 재생성 없이** 보관된 원본 사진 위에 다시
그려서 고친다(비용 0). 교정은 1회만 - 무한 핑퐁을 막는다.
"""

import base64

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import QaReport
from app.graphs.state import OSState
from app.graphs.workers._marketing_shared import brand_book, canonical_product, fetch_products
from app.services.card_render import brand_color_of, fetch_image_bytes, render_slide
from app.tools.ai.image.storage import upload_marketing_image
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

llm = get_llm()

_MAX_REVIEWED = 5  # 검수에 넘기는 이미지 수 상한(입력 토큰 방어 - 1장당 약 1.5k 토큰)
_SCALE_DOWN = {"xl": "l", "l": "m", "m": "m"}

SYSTEM_PROMPT = """당신은 CharisLab의 브랜드 QA입니다. 아래 이미지들은 곧 CEO 결재에 올라갈
카드뉴스 실물입니다. 당신은 만드는 사람이 아니라 **내보내도 되는지 판정하는 사람**입니다.

이미지를 직접 보고 다음을 확인하세요:
1. **글자 잘림/넘침** - 제목이나 보조문구가 카드 밖으로 나가거나 잘렸는가
2. **가독성** - 글자와 배경의 대비가 충분한가(밝은 사진 위 흰 글자, 배경과 같은 색 뱃지 등)
3. **겹침** - 글자가 인물 얼굴이나 다른 요소를 덮어 내용을 방해하는가
4. **브랜드 톤** - 아래 브랜드북의 톤과 어긋나거나 금지 표현이 보이는가
5. **장별 역할** - 첫 장이 시선을 잡는가, 마지막 장이 행동을 부르는가

판정 규칙:
- 문제가 없으면 verdict="pass", issues는 빈 배열로 두세요. **없는 문제를 만들어내지 마세요.**
- 고쳐야 할 게 있으면 verdict="fix"로 하고, 문제마다 장 번호(1부터)와 자동 교정 방법을 고르세요:
  - shrink_headline: 제목이 길어 잘리거나 답답할 때(한 단계 작게)
  - shorten_headline: 줄여야 의미가 사는 경우 - suggested_headline에 더 짧은 제목을 직접 쓰세요
  - add_text_panel: 글자 대비가 부족할 때(글자 뒤에 판을 깔아 대비 확보)
  - move_text: 글자가 인물 얼굴/핵심 피사체를 덮을 때(반대편으로 이동)
  - none: 자동 교정으로는 못 고치는 문제(사진 자체가 내용과 안 맞는 등) - severity는 warn으로
- severity=block은 "이대로 CEO에게 올리면 안 되는" 수준에만 쓰세요.
summary는 CEO 결재 카드에 함께 붙을 검수 소견 1~2문장으로 쓰세요."""


def _apply_fix(slide: dict, issue: dict) -> bool:
    """자동 교정을 슬라이드에 적용한다. 실제로 바뀌었으면 True."""
    fix = issue.get("fix")
    spec = dict(slide.get("layout_spec") or {})
    if fix == "shrink_headline":
        current = spec.get("headline_scale", "l")
        spec["headline_scale"] = _SCALE_DOWN.get(current, "m")
        if spec["headline_scale"] == current:
            return False
    elif fix == "shorten_headline":
        suggested = (issue.get("suggested_headline") or "").strip()
        if not suggested or suggested == slide.get("headline"):
            return False
        slide["headline"] = suggested
        return True
    elif fix == "add_text_panel":
        if spec.get("text_panel") in ("white_card", "scrim", "note"):
            return False
        # 사진이 화면을 덮는 구성이면 scrim(어두운 그라데이션), 아니면 흰 판이 자연스럽다.
        spec["text_panel"] = "scrim" if spec.get("background") == "photo_full" else "white_card"
    elif fix == "move_text":
        spec["text_position"] = "top" if spec.get("text_position", "bottom") != "top" else "bottom"
    else:
        return False
    slide["layout_spec"] = spec
    return True


async def brand_qa_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    post = state.get("marketing_post") or {}
    image_urls = post.get("image_urls") or []
    slides = post.get("slides") or []
    if not image_urls:
        return {"qa_report": {"verdict": "pass", "issues": [], "summary": "검수할 이미지가 없습니다"}}

    run_id = start_run("BrandQA", {"slides": len(image_urls)}, thread_id=thread_id)
    product = post.get("product", "")
    product_row = fetch_products().get(canonical_product(product))

    reviewed = image_urls[:_MAX_REVIEWED]
    images: list[str] = []
    for url in reviewed:
        data = await fetch_image_bytes(url)
        if data:
            images.append(base64.b64encode(data).decode())

    if not images:
        finish_run(run_id, {"verdict": "pass", "summary": "이미지를 불러오지 못해 검수를 건너뜀"})
        return {"qa_report": {"verdict": "pass", "issues": [], "summary": "이미지를 불러오지 못해 검수를 건너뜀"}}

    slide_text = "\n".join(
        f"{i + 1}장: 제목 \"{s.get('headline', '')}\" / 보조 \"{s.get('subtext', '')}\" / 틀 {s.get('layout_name', '')}"
        for i, s in enumerate(slides[: len(images)])
    )
    user_content = (
        f"{brand_book(product_row)}\n\n제품: {product}\n"
        f"검수 대상 {len(images)}장(순서대로):\n{slide_text}\n\n"
        "위 이미지들을 직접 보고 판정하세요."
    )

    try:
        report = await llm.complete_structured(
            [
                Message(role="system", content=SYSTEM_PROMPT),
                Message(role="user", content=user_content, images=images),
            ],
            QaReport,
            thread_id=thread_id,
            agent_name="BrandQA",
        )
    except Exception as exc:
        # 검수는 부가 단계다 - 실패했다고 게시물 전체를 막지 않고 통과시키되 사실대로 남긴다.
        finish_run(run_id, {"verdict": "pass", "summary": f"검수 실패: {exc}"})
        return {
            "qa_report": {"verdict": "pass", "issues": [], "summary": f"검수를 수행하지 못했습니다({exc})"}
        }

    result = report.model_dump()
    if report.verdict == "pass" or not report.issues:
        finish_run(run_id, result)
        return {
            "qa_report": result,
            "messages": [{"role": "assistant", "content": f"[BrandQA] 검수 통과 - {report.summary}"}],
        }

    # 자동 교정 적용 → 해당 장만 다시 그린다(보관된 원본 사진 재사용이라 AI 비용 0).
    new_slides = [dict(s) for s in slides]
    new_urls = list(image_urls)
    brand = brand_color_of(product)
    fmt = post.get("format", "card_news")
    total = len(new_slides)
    fixed: list[int] = []
    for issue in result["issues"]:
        idx = int(issue.get("slide_index", 0)) - 1
        if not (0 <= idx < len(new_slides)):
            continue
        slide = new_slides[idx]
        if not _apply_fix(slide, issue):
            continue
        photo = await fetch_image_bytes(slide.get("source_image_url"))
        if not photo and (slide.get("layout_spec") or {}).get("photo_style", "full") != "none":
            continue  # 원본 사진이 없으면 다시 그리면 사진이 사라진다 - 건너뛴다
        card = render_slide(slide, product, f"{idx + 1}/{total}", brand, fmt, photo)
        new_urls[idx] = upload_marketing_image(card)
        fixed.append(idx + 1)

    result["fixed_slides"] = fixed
    finish_run(run_id, result)
    return {
        "qa_report": result,
        "marketing_post": {**post, "slides": new_slides, "image_urls": new_urls},
        "messages": [
            {
                "role": "assistant",
                "content": f"[BrandQA] {len(result['issues'])}건 지적 - {len(fixed)}장 자동 교정({fixed}) / {report.summary}",
            }
        ],
    }
