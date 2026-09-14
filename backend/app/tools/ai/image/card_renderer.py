from io import BytesIO
from pathlib import Path
from typing import Callable

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


def render_banded(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """레이아웃 스타일 1/4 "banded" - 상단 풀블리드 사진(사각, 그라데이션/둥근모서리 없음) +
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


def render_overlay(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """레이아웃 스타일 2/4 "overlay" - 풀블리드 사진 전체 위에 하단 다크 그라데이션 스크림을 깔고
    그 위에 흰 텍스트를 얹는다. 인스타그램에서 가장 흔한 "사진 위에 텍스트" 스타일."""
    photo = _crop_to_ratio(illustration_bytes, CANVAS, CANVAS).convert("RGBA")

    # 하단 그라데이션 스크림 - 세로 1px 그라데이션 마스크를 만들어 확장(위는 투명, 아래로 갈수록 불투명)
    scrim_h = int(CANVAS * 0.55)
    gradient = Image.new("L", (1, scrim_h))
    for y in range(scrim_h):
        gradient.putpixel((0, y), int(235 * (y / scrim_h) ** 1.6))
    gradient = gradient.resize((CANVAS, scrim_h))
    black_layer = Image.new("RGBA", (CANVAS, scrim_h), (10, 8, 20, 255))
    scrim = Image.composite(black_layer, Image.new("RGBA", (CANVAS, scrim_h), (0, 0, 0, 0)), gradient)
    photo.paste(scrim, (0, CANVAS - scrim_h), scrim)

    canvas = photo.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    pad_x = 64

    badge_font = _font("SemiBold", 26)
    badge_pad_x, badge_pad_y = 22, 10
    badge_w = draw.textlength(product, font=badge_font) + badge_pad_x * 2
    badge_h = 26 + badge_pad_y * 2
    badge_top = CANVAS - scrim_h + 36
    draw.rounded_rectangle(
        [(pad_x, badge_top), (pad_x + badge_w, badge_top + badge_h)], radius=badge_h / 2, fill=brand_color
    )
    draw.text((pad_x + badge_pad_x, badge_top + badge_pad_y - 1), product, font=badge_font, fill=WHITE)

    headline_font = _font("ExtraBold", 58)
    subtext_font = _font("Medium", 30)
    headline_lines = _wrap_text(draw, headline, headline_font, CANVAS - pad_x * 2)[:2]
    subtext_lines = _wrap_text(draw, subtext, subtext_font, CANVAS - pad_x * 2)[:2]

    label_reserve = 56 if page_label else 24
    y = CANVAS - label_reserve - len(subtext_lines) * 40 - len(headline_lines) * 68 - 16
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 68
    y += 6
    for line in subtext_lines:
        draw.text((pad_x, y), line, font=subtext_font, fill=(222, 222, 228))
        y += 40

    if page_label:
        label_font = _font("SemiBold", 24)
        label_w = draw.textlength(page_label, font=label_font)
        draw.text((CANVAS - pad_x - label_w, CANVAS - 56), page_label, font=label_font, fill=(222, 222, 228))

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def render_bold_type(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """레이아웃 스타일 3/4 "bold_type" - 사진은 작은 정사각 썸네일로만 쓰고, 화면 대부분을 초대형
    타이포그래피 헤드라인이 채우는 "질문/후킹 카드" 스타일. 후킹 슬라이드에 특히 효과적."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), BG)
    draw = ImageDraw.Draw(canvas)
    pad_x = 64

    badge_font = _font("SemiBold", 26)
    badge_pad_x, badge_pad_y = 22, 10
    badge_w = draw.textlength(product, font=badge_font) + badge_pad_x * 2
    badge_h = 26 + badge_pad_y * 2
    draw.rounded_rectangle([(pad_x, 64), (pad_x + badge_w, 64 + badge_h)], radius=badge_h / 2, fill=brand_color)
    draw.text((pad_x + badge_pad_x, 64 + badge_pad_y - 1), product, font=badge_font, fill=WHITE)

    thumb_size = 340
    thumb = _crop_to_ratio(illustration_bytes, thumb_size, thumb_size)
    canvas.paste(thumb, (CANVAS - pad_x - thumb_size, 64))

    headline_font = _font("Black", 92)
    headline_lines = _wrap_text(draw, headline, headline_font, CANVAS - pad_x * 2)[:3]
    y = 480
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=INK)
        y += 104

    subtext_font = _font("SemiBold", 34)
    subtext_lines = _wrap_text(draw, subtext, subtext_font, CANVAS - pad_x * 2)[:2]
    y += 20
    for line in subtext_lines:
        draw.text((pad_x, y), line, font=subtext_font, fill=brand_color)
        y += 46

    if page_label:
        label_font = _font("SemiBold", 24)
        label_w = draw.textlength(page_label, font=label_font)
        draw.text((CANVAS - pad_x - label_w, CANVAS - 56), page_label, font=label_font, fill=_lighten(INK, 0.5))

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def render_split(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """레이아웃 스타일 4/4 "split" - 세로 2분할: 좌측 42% 브랜드 컬러 블록 위에 텍스트,
    우측 58% 풀블리드 사진."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), brand_color)
    draw = ImageDraw.Draw(canvas)

    left_w = int(CANVAS * 0.42)
    right_w = CANVAS - left_w
    photo = _crop_to_ratio(illustration_bytes, right_w, CANVAS)
    canvas.paste(photo, (left_w, 0))

    pad_x = 44
    content_w = left_w - pad_x * 2
    subtext_color = _lighten(brand_color, 0.85)

    badge_font = _font("SemiBold", 24)
    badge_pad_x, badge_pad_y = 18, 8
    badge_w = draw.textlength(product, font=badge_font) + badge_pad_x * 2
    badge_h = 24 + badge_pad_y * 2
    draw.rounded_rectangle([(pad_x, 56), (pad_x + badge_w, 56 + badge_h)], radius=badge_h / 2, fill=WHITE)
    draw.text((pad_x + badge_pad_x, 56 + badge_pad_y - 1), product, font=badge_font, fill=brand_color)

    headline_font = _font("ExtraBold", 46)
    subtext_font = _font("Medium", 26)
    headline_lines = _wrap_text(draw, headline, headline_font, content_w)[:4]
    subtext_lines = _wrap_text(draw, subtext, subtext_font, content_w)[:3]

    total_h = len(headline_lines) * 54 + 16 + len(subtext_lines) * 34
    y = (CANVAS - total_h) // 2
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 54
    y += 16
    for line in subtext_lines:
        draw.text((pad_x, y), line, font=subtext_font, fill=subtext_color)
        y += 34

    if page_label:
        label_font = _font("SemiBold", 22)
        draw.text((pad_x, CANVAS - 50), page_label, font=label_font, fill=subtext_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


RENDERERS: dict[str, Callable[..., bytes]] = {
    "banded": render_banded,
    "overlay": render_overlay,
    "bold_type": render_bold_type,
    "split": render_split,
}


def render_comic_panel(
    illustration_bytes: bytes,
    dialogue: str,
    narration: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """인스타툰(말풍선 만화) 한 컷 - 마스코트가 등장하는 장면(illustration_bytes, mascot.py의
    참조 이미지를 기반으로 편집 생성됨)을 풀블리드로 깔고, 상단에 대화 말풍선(dialogue), 있으면
    하단에 자막바(narration, 상황 설명/캡션)를 얹는다. RENDERERS 딕셔너리는 카드뉴스 4종 전용이라
    이 함수는 별도로 export한다(card_composer.compose_instatoon_panel이 직접 호출)."""
    canvas = _crop_to_ratio(illustration_bytes, CANVAS, CANVAS)
    draw = ImageDraw.Draw(canvas)
    pad_x = 64

    # 상단 말풍선(대화)
    bubble_font = _font("Bold", 40)
    bubble_max_w = CANVAS - pad_x * 2 - 80
    bubble_lines = _wrap_text(draw, dialogue, bubble_font, bubble_max_w)[:3] if dialogue else []
    line_h = 50
    bubble_pad_x, bubble_pad_y = 40, 32
    bubble_top = 56
    bubble_w = CANVAS - pad_x * 2
    bubble_h = max(len(bubble_lines), 1) * line_h + bubble_pad_y * 2
    draw.rounded_rectangle(
        [(pad_x, bubble_top), (pad_x + bubble_w, bubble_top + bubble_h)],
        radius=32,
        fill=WHITE,
        outline=INK,
        width=4,
    )
    tail_cx = pad_x + bubble_w // 2
    tail_top = bubble_top + bubble_h
    draw.polygon(
        [(tail_cx - 22, tail_top - 3), (tail_cx + 22, tail_top - 3), (tail_cx, tail_top + 30)],
        fill=WHITE,
        outline=INK,
    )
    ty = bubble_top + bubble_pad_y
    for line in bubble_lines:
        draw.text((pad_x + bubble_pad_x, ty), line, font=bubble_font, fill=INK)
        ty += line_h

    # 제품 뱃지 (우상단, 말풍선과 안 겹치게 그 아래)
    badge_font = _font("SemiBold", 24)
    badge_pad_x, badge_pad_y = 18, 8
    badge_w = draw.textlength(product, font=badge_font) + badge_pad_x * 2
    badge_h = 24 + badge_pad_y * 2
    badge_top = bubble_top + bubble_h + 46
    draw.rounded_rectangle(
        [(CANVAS - pad_x - badge_w, badge_top), (CANVAS - pad_x, badge_top + badge_h)],
        radius=badge_h / 2,
        fill=brand_color,
    )
    draw.text(
        (CANVAS - pad_x - badge_w + badge_pad_x, badge_top + badge_pad_y - 1),
        product,
        font=badge_font,
        fill=WHITE,
    )

    # 하단 자막바 (narration이 있을 때만)
    if narration:
        bar_h = 104
        draw.rectangle([(0, CANVAS - bar_h), (CANVAS, CANVAS)], fill=INK)
        caption_font = _font("Medium", 28)
        caption_lines = _wrap_text(draw, narration, caption_font, CANVAS - pad_x * 2)[:2]
        cy = CANVAS - bar_h + (bar_h - len(caption_lines) * 36) // 2
        for line in caption_lines:
            line_w = draw.textlength(line, font=caption_font)
            draw.text(((CANVAS - line_w) // 2, cy), line, font=caption_font, fill=WHITE)
            cy += 36

    if page_label:
        label_font = _font("SemiBold", 22)
        label_color = WHITE if narration else _lighten(INK, 0.4)
        label_w = draw.textlength(page_label, font=label_font)
        label_y = CANVAS - 44 if narration else CANVAS - 40
        draw.text((CANVAS - pad_x - label_w, label_y), page_label, font=label_font, fill=label_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()
