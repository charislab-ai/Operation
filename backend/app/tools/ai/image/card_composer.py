from app.tools.ai.image import get_image_gen
from app.tools.ai.image.card_renderer import DEFAULT_BRAND, render_card_news


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
) -> bytes:
    """배경 이미지 위에 실제 헤드라인/보조문구를 합성한 카드뉴스 이미지를 만든다.

    텍스트를 AI 생성에 맡기면 누락/오타가 나올 수 있어(실측으로 확인된 한계), 배경만 AI가 만들고
    텍스트는 PIL로 정확하게 얹는다. brand_color는 제품별 브랜드 컬러(CharisLab 색을 그대로 쓰면 안 됨).
    illustration_bytes를 직접 넘기면 AI 생성을 건너뛰고 그 이미지(예: 실제 앱 스크린샷)를 그대로 쓴다.
    thread_id/agent_name은 업무 지시별 AI 사용량 로깅용 선택적 컨텍스트.
    """
    if illustration_bytes is None:
        illustration_bytes = await get_image_gen().generate_bytes(
            image_prompt, thread_id=thread_id, agent_name=agent_name
        )
    return render_card_news(illustration_bytes, headline, subtext, product, page_label, brand_color)
