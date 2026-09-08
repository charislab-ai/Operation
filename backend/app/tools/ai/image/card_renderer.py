from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"

CANVAS = 1080
BG = (247, 245, 242)  # 따뜻한 오프화이트 - 그라데이션 대신 단색
INK = (30, 27, 46)  # 거의 검정에 가까운 진보라 - 순수 블랙 대신
WHITE = (255, 255, 255)
DEFAULT_BRAND = (136, 106, 255)  # #886AFF - CharisLab 기본색(제품별 색이 없을 때만 사용)

PHOTO_H = 620
BAND_ACCENT_H = 6


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / f"Pretendard-{weight}.otf"), size)


def _lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(int(c + (255 - c) * amount) for c in rgb)


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
    """target 비율에 맞게 크롭한다. 세로를 잘라야 할 때는 위쪽을 최대한 보존한다(사람 얼굴이
    보통 위쪽에 있어 중앙 크롭 시 머리가 잘려나가는 문제가 실측으로 확인됨) - 아래쪽에서 더 많이
    잘라내고 위쪽은 살짝만 잘라낸다."""
    photo = Image.open(BytesIO(illustration_bytes)).convert("RGB")
    target_ratio = target_w / target_h
    src_ratio = photo.width / photo.height
    if src_ratio > target_ratio:
        new_width = int(photo.height * target_ratio)
        offset = (photo.width - new_width) // 2
        photo = photo.crop((offset, 0, offset + new_width, photo.height))
    else:
        new_height = int(photo.width / target_ratio)
        # 잘라낼 여유분의 20%만 위에서, 나머지 80%는 아래에서 잘라낸다(머리 보존)
        slack = photo.height - new_height
        top_offset = int(slack * 0.2)
        photo = photo.crop((0, top_offset, photo.width, top_offset + new_height))
    return photo.resize((target_w, target_h), Image.LANCZOS)


def render_card_news(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """실제 한국 카드뉴스 스타일에 가깝게: 상단 풀블리드 사진(사각, 그라데이션/둥근모서리 없음) +
    하단 단색 브랜드 컬러 밴드에 좌측정렬 헤드라인. AI 특유의 보라-파랑 그라데이션 배경, 중앙정렬
    텍스트, 둥둥 떠있는 둥근 카드 같은 "티 나는" 패턴을 의도적으로 피한다. brand_color는 제품별로
    다르게 넘겨야 한다(CharisLab 보라색을 모든 제품에 그대로 쓰면 안 됨 - 실측 피드백)."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), BG)
    draw = ImageDraw.Draw(canvas)

    accent_color = tuple(max(0, c - 30) for c in brand_color)  # 브랜드색보다 살짝 어둡게
    subtext_color = _lighten(brand_color, 0.85)  # 브랜드색보다 살짝 밝게(보조문구용)

    # 상단: 풀블리드 사진 (사각, 크롭)
    photo = _crop_to_ratio(illustration_bytes, CANVAS, PHOTO_H)
    canvas.paste(photo, (0, 0))

    # 사진과 텍스트 밴드 사이 얇은 포인트 라인(브랜드색을 살짝 어둡게)
    draw.rectangle([(0, PHOTO_H), (CANVAS, PHOTO_H + BAND_ACCENT_H)], fill=accent_color)

    # 하단: 단색 브랜드 컬러 밴드
    band_top = PHOTO_H + BAND_ACCENT_H
    draw.rectangle([(0, band_top), (CANVAS, CANVAS)], fill=brand_color)

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
    draw.text((pad_x + badge_pad_x, content_top + badge_pad_y - 1), product, font=badge_font, fill=brand_color)

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
        draw.text((pad_x, y), line, font=subtext_font, fill=subtext_color)
        y += 40

    if page_label:
        label_font = _font("SemiBold", 24)
        label_w = draw.textlength(page_label, font=label_font)
        draw.text((CANVAS - pad_x - label_w, CANVAS - 56), page_label, font=label_font, fill=subtext_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
