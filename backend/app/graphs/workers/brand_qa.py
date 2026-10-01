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
import logging

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
logger = logging.getLogger(__name__)

_MAX_REVIEWED = 5  # 검수에 넘기는 이미지 수 상한(입력 토큰 방어 - 1장당 약 1.5k 토큰)
_MAX_ROUNDS = 3  # 검수 반복 상한 - 고칠 게 없으면 그 전에 멈춘다(무한 핑퐁 방지)
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


async def _review(
    slides: list[dict],
    urls: list[str],
    indices: list[int],
    product: str,
    product_row: dict | None,
    thread_id: str,
    round_no: int,
) -> QaReport | None:
    """지정한 장들을 실제 이미지로 검수한다. 실패하면 None(검수는 게시를 막지 않는다)."""
    images: list[str] = []
    checked: list[int] = []
    for i in indices:
        data = await fetch_image_bytes(urls[i]) if i < len(urls) else b""
        if data:
            images.append(base64.b64encode(data).decode())
            checked.append(i)
    if not images:
        return None

    slide_text = "\n".join(
        f"{i + 1}장: 제목 \"{slides[i].get('headline', '')}\" / 보조 \"{slides[i].get('subtext', '')}\" "
        f"/ 틀 {slides[i].get('layout_name', '')}"
        for i in checked
    )
    retry_note = (
        ""
        if round_no == 1
        else (
            f"\n\n[재검수 {round_no}회차] 아래는 지적사항을 반영해 **다시 그린** 장들입니다. "
            "고쳐졌는지 확인하고, 해결됐으면 주저 없이 verdict=pass로 통과시키세요. "
            "같은 지적을 반복하지 말고, 남은 문제만 지적하세요."
        )
    )
    user_content = (
        f"{brand_book(product_row)}\n\n제품: {product}\n"
        f"검수 대상 {len(images)}장(장 번호 순서대로: {[i + 1 for i in checked]}):\n{slide_text}"
        f"{retry_note}\n\n위 이미지들을 직접 보고 판정하세요."
    )
    try:
        return await llm.complete_structured(
            [
                Message(role="system", content=SYSTEM_PROMPT),
                Message(role="user", content=user_content, images=images),
            ],
            QaReport,
            thread_id=thread_id,
            agent_name="BrandQA",
        )
    except Exception:
        logger.exception("브랜드 QA 검수 호출 실패(라운드 %d)", round_no)
        return None


async def _apply_and_rerender(
    issues: list[dict], slides: list[dict], urls: list[str], product: str, fmt: str
) -> list[int]:
    """지적사항을 반영해 해당 장만 다시 그린다. 실제로 고친 장 번호(0-based)를 돌려준다.

    보관해둔 원본 사진을 재사용하므로 AI 이미지 생성이 일어나지 않는다(비용 0).
    """
    brand = brand_color_of(product)
    total = len(slides)
    changed: list[int] = []
    for issue in issues:
        idx = int(issue.get("slide_index", 0)) - 1
        if not (0 <= idx < len(slides)) or idx in changed:
            continue
        slide = slides[idx]
        if not _apply_fix(slide, issue):
            continue
        photo = await fetch_image_bytes(slide.get("source_image_url"))
        if not photo and (slide.get("layout_spec") or {}).get("photo_style", "full") != "none":
            continue  # 원본 사진이 없으면 다시 그릴 때 사진이 사라진다 - 건너뛴다
        urls[idx] = upload_marketing_image(
            render_slide(slide, product, f"{idx + 1}/{total}", brand, fmt, photo)
        )
        changed.append(idx)
    return changed


async def brand_qa_node(state: OSState, config: RunnableConfig) -> dict:
    """검수 → 교정 → **재검수**를 통과할 때까지(최대 _MAX_ROUNDS회) 반복한다.

    Why 루프인가: 예전엔 한 번 지적하고 교정한 뒤 그대로 CEO에게 올렸다. 즉 "고친 결과가
    실제로 나아졌는지 아무도 확인하지 않는" 상태였고, 교정이 오히려 다른 문제를 만들어도
    알 수 없었다. 이제 고친 장만 다시 보고 통과 여부를 확인한다.

    비용은 라운드당 비전 호출 1회(고친 장만 넣으므로 2회차부터는 1~2장)로 제한되고,
    교정할 게 없으면 즉시 멈춘다(무한 핑퐁 방지).
    """
    thread_id = config["configurable"]["thread_id"]
    post = state.get("marketing_post") or {}
    image_urls = list(post.get("image_urls") or [])
    slides = [dict(s) for s in (post.get("slides") or [])]
    if not image_urls:
        return {"qa_report": {"verdict": "pass", "issues": [], "summary": "검수할 이미지가 없습니다"}}

    run_id = start_run("BrandQA", {"slides": len(image_urls)}, thread_id=thread_id)
    product = post.get("product", "")
    product_row = fetch_products().get(canonical_product(product))
    fmt = post.get("format", "card_news")

    targets = list(range(min(len(image_urls), _MAX_REVIEWED)))
    rounds: list[dict] = []
    fixed_all: list[int] = []
    final: QaReport | None = None

    for round_no in range(1, _MAX_ROUNDS + 1):
        report = await _review(slides, image_urls, targets, product, product_row, thread_id, round_no)
        if report is None:
            break
        final = report
        issues = [i.model_dump() for i in report.issues]
        rounds.append({"round": round_no, "verdict": report.verdict, "issues": issues, "summary": report.summary})
        if report.verdict == "pass" or not issues:
            break
        changed = await _apply_and_rerender(issues, slides, image_urls, product, fmt)
        if not changed:
            break  # 자동 교정으로 고칠 수 없는 지적만 남음 - 더 돌려도 같은 결과다
        fixed_all = sorted(set(fixed_all) | {i + 1 for i in changed})
        targets = changed  # 다음 라운드는 고친 장만 다시 본다(비용 절감)

    if final is None:
        finish_run(run_id, {"verdict": "pass", "summary": "검수를 수행하지 못했습니다"})
        return {"qa_report": {"verdict": "pass", "issues": [], "summary": "검수를 수행하지 못했습니다"}}

    remaining = [i for i in (rounds[-1]["issues"] if rounds else []) if i.get("severity") == "block"]
    summary = rounds[-1]["summary"] if rounds else ""
    if fixed_all:
        summary = f"{len(fixed_all)}장 자동 교정 후 재검수 통과. {summary}" if not remaining else (
            f"{len(fixed_all)}장 교정했지만 해결되지 않은 문제가 남았습니다. {summary}"
        )

    result = {
        "verdict": "pass" if not remaining else "fix",
        "issues": rounds[-1]["issues"] if rounds else [],
        "summary": summary,
        "fixed_slides": fixed_all,
        "rounds": rounds,
    }
    finish_run(run_id, result)

    message = (
        f"[BrandQA] {len(rounds)}회 검수 - "
        + (f"{len(fixed_all)}장 교정({fixed_all}) 후 " if fixed_all else "")
        + ("통과" if not remaining else f"미해결 {len(remaining)}건")
        + f" / {summary}"
    )
    update: dict = {"qa_report": result, "messages": [{"role": "assistant", "content": message}]}
    if fixed_all:
        update["marketing_post"] = {**post, "slides": slides, "image_urls": image_urls}
    return update
