from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"

CANVAS = 1080
BG = (247, 245, 242)  # 따뜻한 오프화이트 - 그라데이션 대신 단색
BRAND = (136, 106, 255)  # #886AFF
BRAND_ACCENT = (87, 113, 248)  # #5771f8
INK = (30, 27, 46)  # 거의 검정에 가까운 진보라 - 순수 블랙 대신
WHITE = (255, 255, 255)

PHOTO_H = 620
BAND_ACCENT_H = 6


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / f"Pretendard-{weight}.otf"), size)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _crop_to_ratio(illustration_bytes: bytes, target_w: int, target_h: int) -> Image.Image:
    photo = Image.open(BytesIO(illustration_bytes)).convert("RGB")
    target_ratio = target_w / target_h
    src_ratio = photo.width / photo.height
    if src_ratio > target_ratio:
        new_width = int(photo.height * target_ratio)
        offset = (photo.width - new_width) // 2
        photo = photo.crop((offset, 0, offset + new_width, photo.height))
    else:
        new_height = int(photo.width / target_ratio)
        offset = (photo.height - new_height) // 2
        photo = photo.crop((0, offset, photo.width, offset + new_height))
    return photo.resize((target_w, target_h), Image.LANCZOS)


def render_card_news(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
) -> bytes:
    """실제 한국 카드뉴스 스타일에 가깝게: 상단 풀블리드 사진(사각, 그라데이션/둥근모서리 없음) +
    하단 단색 브랜드 컬러 밴드에 좌측정렬 헤드라인. AI 특유의 보라-파랑 그라데이션 배경, 중앙정렬
    텍스트, 둥둥 떠있는 둥근 카드 같은 "티 나는" 패턴을 의도적으로 피한다."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), BG)
    draw = ImageDraw.Draw(canvas)

    # 상단: 풀블리드 사진 (사각, 크롭)
    photo = _crop_to_ratio(illustration_bytes, CANVAS, PHOTO_H)
    canvas.paste(photo, (0, 0))

    # 사진과 텍스트 밴드 사이 얇은 포인트 라인
    draw.rectangle([(0, PHOTO_H), (CANVAS, PHOTO_H + BAND_ACCENT_H)], fill=BRAND_ACCENT)

    # 하단: 단색 브랜드 컬러 밴드
    band_top = PHOTO_H + BAND_ACCENT_H
    draw.rectangle([(0, band_top), (CANVAS, CANVAS)], fill=BRAND)

    pad_x = 64
    content_top = band_top + 44

    # 제품 뱃지 (좌측정렬, 흰 필)
    badge_font = _font("SemiBold", 26)
    badge_pad_x, badge_pad_y = 22, 10
    badge_w = draw.textlength(product, font=badge_font) + badge_pad_x * 2
    badge_h = 26 + badge_pad_y * 2
    draw.rounded_rectangle(
        [(pad_x, content_top), (pad_x + badge_w, content_top + badge_h)], radius=badge_h / 2, fill=WHITE
    )
    draw.text((pad_x + badge_pad_x, content_top + badge_pad_y - 1), product, font=badge_font, fill=BRAND)

    # 헤드라인 (좌측정렬, 볼드)
    headline_font = _font("ExtraBold", 58)
    headline_lines = _wrap_text(draw, headline, headline_font, CANVAS - pad_x * 2)[:2]
    y = content_top + badge_h + 28
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 68

    # 보조문구
    subtext_font = _font("Medium", 30)
    subtext_lines = _wrap_text(draw, subtext, subtext_font, CANVAS - pad_x * 2)[:2]
    y += 10
    for line in subtext_lines:
        draw.text((pad_x, y), line, font=subtext_font, fill=(233, 230, 255))
        y += 40

    if page_label:
        label_font = _font("SemiBold", 24)
        label_w = draw.textlength(page_label, font=label_font)
        draw.text((CANVAS - pad_x - label_w, CANVAS - 56), page_label, font=label_font, fill=(233, 230, 255))

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
