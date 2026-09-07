from app.tools.ai.image import get_image_gen
from app.tools.ai.image.card_renderer import render_card_news


async def compose_marketing_card(
    image_prompt: str, headline: str, subtext: str, product: str, page_label: str | None = None
) -> bytes:
    """AI로 배경 일러스트를 생성하고, 그 위에 실제 헤드라인/보조문구를 합성한 카드뉴스 이미지를 만든다.

    텍스트를 AI 생성에 맡기면 누락/오타가 나올 수 있어(실측으로 확인된 한계), 배경만 AI가 만들고
    텍스트는 PIL로 정확하게 얹는다.
    """
    illustration_bytes = await get_image_gen().generate_bytes(image_prompt)
    return render_card_news(illustration_bytes, headline, subtext, product, page_label)
