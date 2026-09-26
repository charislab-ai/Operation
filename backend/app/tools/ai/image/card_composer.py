from app.tools.ai.image import get_image_gen, get_instatoon_image_gen
from app.tools.ai.image.card_renderer import DEFAULT_BRAND, render_comic_panel
from app.tools.ai.image.layout_engine import render_composed


async def compose_marketing_card(
    image_prompt: str,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
    illustration_bytes: bytes | None = None,
    thread_id: str | None = None,
    agent_name: str | None = None,
    layout_spec: dict | None = None,
    return_source: bool = False,
) -> bytes | tuple[bytes, bytes]:
    """배경 이미지 위에 실제 헤드라인/보조문구를 합성한 카드뉴스 이미지를 만든다.

    텍스트를 AI 생성에 맡기면 누락/오타가 나올 수 있어(실측으로 확인된 한계), 배경만 AI가 만들고
    텍스트는 PIL로 정확하게 얹는다. brand_color는 제품별 브랜드 컬러(CharisLab 색을 그대로 쓰면 안 됨).
    illustration_bytes를 직접 넘기면 AI 생성을 건너뛰고 그 이미지(예: 실제 앱 스크린샷)를 그대로 쓴다.
    thread_id/agent_name은 업무 지시별 AI 사용량 로깅용 선택적 컨텍스트.
    layout_spec은 비주얼 디자이너가 슬라이드별로 설계한 조합형 레이아웃이다 - 고정된 틀 목록에서
    고르는 게 아니라 배경/사진처리/텍스트패널/강조를 조합하므로, 벤치마킹으로 발견한 새 틀도
    코드 수정 없이 바로 쓸 수 있다(app/tools/ai/image/layout_engine.py 참고).
    """
    if illustration_bytes is None:
        illustration_bytes = await get_image_gen().generate_bytes(
            image_prompt, thread_id=thread_id, agent_name=agent_name
        )
    card = render_composed(
        illustration_bytes, headline, subtext, product, page_label, brand_color, spec=layout_spec
    )
    # return_source=True면 합성 전 원본 사진도 함께 돌려준다(편집기에서 재활용).
    return (card, illustration_bytes) if return_source else card


async def compose_instatoon_panel(
    mascot_reference_bytes: bytes,
    scene_prompt: str,
    dialogue: str,
    narration: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
    thread_id: str | None = None,
    agent_name: str | None = None,
    return_source: bool = False,
) -> bytes | tuple[bytes, bytes]:
    """인스타툰(말풍선 만화) 한 컷을 만든다. mascot_reference_bytes(mascot.py에서 만든 고정 캐릭터
    참조 이미지)를 edit_bytes에 넘겨 이 컷의 장면(scene_prompt: 포즈/표정/배경)을 그리게 하고,
    거기에 말풍선(dialogue)/자막(narration)을 PIL로 합성한다 - compose_marketing_card와 마찬가지로
    텍스트는 AI에 맡기지 않고 정확하게 얹는다."""
    panel_bytes = await get_instatoon_image_gen().edit_bytes(
        mascot_reference_bytes, scene_prompt, thread_id=thread_id, agent_name=agent_name
    )
    panel = render_comic_panel(panel_bytes, dialogue, narration, product, page_label, brand_color)
    # return_source=True면 말풍선 얹기 전 원본 컷도 함께 돌려준다(편집기에서 재활용).
    return (panel, panel_bytes) if return_source else panel
