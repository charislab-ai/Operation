from io import BytesIO
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "fonts"

CANVAS = 1080
BG = (247, 245, 242)  # 따뜻한 오프화이트 - 그라데이션 대신 단색
INK = (30, 27, 46)  # 거의 검정에 가까운 진보라 - 순수 블랙 대신
WHITE = (255, 255, 255)
DEFAULT_BRAND = (136, 106, 255)  # #886AFF - CharisLab 기본색(제품별 색이 없을 때만 사용)

PHOTO_H = 620
BAND_ACCENT_H = 6

# 인스타툰 전용 캔버스 - 정사각형(1:1)이 아니라 4:5 세로형. 인스타그램 피드에서 정사각형보다
# 화면을 더 많이 차지해 노출/스크롤 정지율에 유리하다는 게 실제 인스타툰 제작 가이드의 권장사항
# (카드뉴스 4종은 브랜드 일관성상 기존 정사각형 그대로 유지, 인스타툰만 우선 적용).
COMIC_W = 1080
COMIC_H = 1350


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


def _fit_or_crop(
    illustration_bytes: bytes, target_w: int, target_h: int, bg: tuple[int, int, int]
) -> Image.Image:
    """가로로 긴 영역에 세로 이미지(앱 스크린샷 등)를 넣을 때는 크롭하지 않고 배경색 위에
    통째로 얹는다.

    Why: 등록된 앱 스크린샷은 9:16 세로 폰 목업인데 _crop_to_ratio로 1080x620에 맞추면 화면
    가운데 일부만 남고 앱 UI가 통째로 잘려나갔다(실측: 라이브러리 화면이 무슨 화면인지 알아볼 수
    없게 나옴). 원본이 타겟보다 세로로 훨씬 길면 contain 방식으로 바꾼다."""
    src = Image.open(BytesIO(illustration_bytes)).convert("RGB")
    src_ratio = src.width / src.height
    target_ratio = target_w / target_h
    # 원본이 타겟보다 확연히 세로로 길면(스크린샷류) 잘라내지 않고 맞춰 넣는다
    if src_ratio < target_ratio * 0.75:
        canvas = Image.new("RGB", (target_w, target_h), bg)
        scale = min(target_w / src.width, target_h / src.height)
        resized = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
        canvas.paste(resized, ((target_w - resized.width) // 2, (target_h - resized.height) // 2))
        return canvas
    return _crop_to_ratio(illustration_bytes, target_w, target_h)


def _vertical_gradient(
    size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> Image.Image:
    """위->아래 세로 그라디언트. 2026년 카드뉴스 트렌드 조사에서 "고대비 단색 블록"보다 "부드러운
    그라디언트 블록"이 우세하다는 결론이 나와 banded 틀에 반영한다(docs/marketing_benchmarks)."""
    w, h = size
    strip = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        strip.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return strip.resize((w, h), Image.LANCZOS)


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
    photo = _fit_or_crop(illustration_bytes, CANVAS, PHOTO_H, _lighten(brand_color, 0.86))
    canvas.paste(photo, (0, 0))

    # 사진과 텍스트 밴드 사이 얇은 포인트 라인(브랜드색을 살짝 어둡게)
    draw.rectangle([(0, PHOTO_H), (CANVAS, PHOTO_H + BAND_ACCENT_H)], fill=accent_color)

    # 하단: 브랜드 컬러 그라디언트 밴드(단색 블록보다 그라디언트가 우세하다는 벤치마킹 결론 반영)
    band_top = PHOTO_H + BAND_ACCENT_H
    band = _vertical_gradient((CANVAS, CANVAS - band_top), _lighten(brand_color, 0.18), accent_color)
    canvas.paste(band, (0, band_top))

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
    headline_font = _font("ExtraBold", 70)
    headline_lines = _wrap_text(draw, headline, headline_font, CANVAS - pad_x * 2)[:2]
    y = content_top + badge_h + 24
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 82

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
    photo = _fit_or_crop(illustration_bytes, CANVAS, CANVAS, INK).convert("RGBA")

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

    headline_font = _font("ExtraBold", 72)
    subtext_font = _font("Medium", 32)
    headline_lines = _wrap_text(draw, headline, headline_font, CANVAS - pad_x * 2)[:3]
    subtext_lines = _wrap_text(draw, subtext, subtext_font, CANVAS - pad_x * 2)[:2]

    label_reserve = 56 if page_label else 24
    y = CANVAS - label_reserve - len(subtext_lines) * 42 - len(headline_lines) * 84 - 16
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 84
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
    thumb = _fit_or_crop(illustration_bytes, thumb_size, thumb_size, _lighten(brand_color, 0.86))
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
    photo = _fit_or_crop(illustration_bytes, right_w, CANVAS, brand_color)
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

    headline_font = _font("ExtraBold", 56)
    subtext_font = _font("Medium", 28)
    headline_lines = _wrap_text(draw, headline, headline_font, content_w)[:4]
    subtext_lines = _wrap_text(draw, subtext, subtext_font, content_w)[:3]

    total_h = len(headline_lines) * 66 + 16 + len(subtext_lines) * 36
    y = (CANVAS - total_h) // 2
    for line in headline_lines:
        draw.text((pad_x, y), line, font=headline_font, fill=WHITE)
        y += 66
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
    참조 이미지를 기반으로 편집 생성됨)을 4:5 세로형(COMIC_W x COMIC_H) 풀블리드로 깔고, 상단에
    대화 말풍선(dialogue), 있으면 하단에 자막바(narration, 상황 설명/캡션)를 얹는다. 정사각형이
    아니라 4:5인 이유는 인스타그램 피드에서 화면을 더 차지해 노출에 유리하기 때문(카드뉴스 4종은
    브랜드 일관성상 정사각형 유지, 인스타툰만 세로형). RENDERERS 딕셔너리는 카드뉴스 4종 전용이라
    이 함수는 별도로 export한다(card_composer.compose_instatoon_panel이 직접 호출)."""
    canvas = _fit_or_crop(illustration_bytes, COMIC_W, COMIC_H, BG)
    draw = ImageDraw.Draw(canvas)
    pad_x = 64

    # 상단 말풍선(대화)
    bubble_font = _font("Bold", 40)
    bubble_max_w = COMIC_W - pad_x * 2 - 80
    bubble_lines = _wrap_text(draw, dialogue, bubble_font, bubble_max_w)[:3] if dialogue else []
    line_h = 50
    bubble_pad_x, bubble_pad_y = 40, 32
    bubble_top = 64
    bubble_w = COMIC_W - pad_x * 2
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
        [(COMIC_W - pad_x - badge_w, badge_top), (COMIC_W - pad_x, badge_top + badge_h)],
        radius=badge_h / 2,
        fill=brand_color,
    )
    draw.text(
        (COMIC_W - pad_x - badge_w + badge_pad_x, badge_top + badge_pad_y - 1),
        product,
        font=badge_font,
        fill=WHITE,
    )

    # 하단 자막바 (narration이 있을 때만)
    if narration:
        bar_h = 112
        draw.rectangle([(0, COMIC_H - bar_h), (COMIC_W, COMIC_H)], fill=INK)
        caption_font = _font("Medium", 28)
        caption_lines = _wrap_text(draw, narration, caption_font, COMIC_W - pad_x * 2)[:2]
        cy = COMIC_H - bar_h + (bar_h - len(caption_lines) * 36) // 2
        for line in caption_lines:
            line_w = draw.textlength(line, font=caption_font)
            draw.text(((COMIC_W - line_w) // 2, cy), line, font=caption_font, fill=WHITE)
            cy += 36

    if page_label:
        label_font = _font("SemiBold", 22)
        label_color = WHITE if narration else _lighten(INK, 0.4)
        label_w = draw.textlength(page_label, font=label_font)
        label_y = COMIC_H - 48 if narration else COMIC_H - 44
        draw.text((COMIC_W - pad_x - label_w, label_y), page_label, font=label_font, fill=label_color)

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 2세대 레이아웃 - CEO 피드백("배경도 별로, 틀도 별로") 반영해 새로 디자인.
# 1세대(banded/split)의 문제: 브랜드 컬러를 화면 40~45%에 단색으로 크게 칠하고 그 안에 작은
# 텍스트만 놓아서 "비어 보이고 촌스럽다". 2세대는 브랜드 컬러를 배경이 아니라 "포인트"로만
# 쓰고, 사진/타이포 자체가 화면을 채우게 한다.
# ─────────────────────────────────────────────────────────────────────────────

INK_DEEP = (18, 16, 30)


def _shadow_box(canvas: Image.Image, box: tuple[int, int, int, int], radius: int, blur: int = 18) -> None:
    """요소 아래에 부드러운 그림자를 깔아 "떠 있는" 느낌을 준다(밋밋함 해소)."""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([(x0, y0 + 10), (x1, y1 + 10)], radius=radius, fill=(0, 0, 0, 90))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(blur))), (0, 0))


def _draw_marker_text(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    x: int,
    y: int,
    line_h: int,
    text_color: tuple[int, int, int],
    marker_color: tuple[int, int, int] | None,
) -> int:
    """형광펜으로 그은 듯한 밑줄 박스 위에 텍스트를 쓴다 - 한국 카드뉴스에서 시선을 잡는 기본 장치."""
    for line in lines:
        if marker_color:
            w = draw.textlength(line, font=font)
            top = y + int(font.size * 0.55)
            draw.rounded_rectangle([(x - 6, top), (x + w + 10, y + int(font.size * 1.12))], radius=6, fill=marker_color)
        draw.text((x, y), line, font=font, fill=text_color)
        y += line_h
    return y


def render_editorial(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """매거진형 - 사진이 화면 전체를 채우고, 하단에 흰 카드가 떠 있는 위에 검정 큰 텍스트.
    브랜드 컬러는 작은 라벨에만 쓴다(배경 전체를 칠하지 않아 촌스러움이 사라짐)."""
    canvas = _fit_or_crop(illustration_bytes, CANVAS, CANVAS, INK_DEEP).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    pad = 56
    head_font = _font("ExtraBold", 66)
    sub_font = _font("Medium", 30)
    head_lines = _wrap_text(draw, headline, head_font, CANVAS - pad * 2 - 88)[:3]
    sub_lines = _wrap_text(draw, subtext, sub_font, CANVAS - pad * 2 - 88)[:2]

    card_h = 96 + len(head_lines) * 78 + (len(sub_lines) * 42 if sub_lines else 0)
    card_top = CANVAS - pad - card_h
    _shadow_box(canvas, (pad, card_top, CANVAS - pad, CANVAS - pad), 36)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([(pad, card_top), (CANVAS - pad, CANVAS - pad)], radius=36, fill=WHITE)

    tx = pad + 44
    ty = card_top + 36
    label_font = _font("Bold", 24)
    draw.text((tx, ty), product.upper(), font=label_font, fill=brand_color)
    ty += 46
    for line in head_lines:
        draw.text((tx, ty), line, font=head_font, fill=INK_DEEP)
        ty += 78
    ty += 6
    for line in sub_lines:
        draw.text((tx, ty), line, font=sub_font, fill=(110, 108, 125))
        ty += 42

    if page_label:
        lf = _font("SemiBold", 24)
        draw.text((CANVAS - pad - draw.textlength(page_label, font=lf), pad), page_label, font=lf, fill=WHITE)

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def render_marker(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """키워드 강조형 - 어두운 배경에 초대형 타이포가 주인공이고, 헤드라인에 형광펜 마커를 그어
    시선을 잡는다. 사진은 하단 스트립으로 작게(텍스트가 주인공인 후킹/주장 슬라이드용)."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), INK_DEEP)
    draw = ImageDraw.Draw(canvas)
    pad = 64

    strip_h = 300
    photo = _fit_or_crop(illustration_bytes, CANVAS - pad * 2, strip_h, INK_DEEP)
    mask = Image.new("L", (CANVAS - pad * 2, strip_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (CANVAS - pad * 2, strip_h)], radius=28, fill=255)
    canvas.paste(photo, (pad, CANVAS - pad - strip_h), mask)

    badge_font = _font("Bold", 24)
    draw.text((pad, pad), product.upper(), font=badge_font, fill=brand_color)

    head_font = _font("Black", 82)
    head_lines = _wrap_text(draw, headline, head_font, CANVAS - pad * 2)[:3]
    y = pad + 76
    y = _draw_marker_text(draw, head_lines, head_font, pad, y, 98, WHITE, brand_color)

    sub_font = _font("Medium", 30)
    for line in _wrap_text(draw, subtext, sub_font, CANVAS - pad * 2)[:2]:
        draw.text((pad, y + 12), line, font=sub_font, fill=(175, 172, 195))
        y += 42

    if page_label:
        lf = _font("SemiBold", 24)
        draw.text((CANVAS - pad - draw.textlength(page_label, font=lf), pad + 4), page_label, font=lf, fill=(140, 137, 160))

    buf = BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def render_device(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """앱 화면 쇼케이스형 - 부드러운 브랜드 그라디언트 위에 폰 스크린샷을 크게 띄운다.
    실제 앱 화면을 보여주는 슬라이드 전용(기존엔 스크린샷이 잘리거나 여백에 떠 있어 초라했음)."""
    canvas = _vertical_gradient((CANVAS, CANVAS), _lighten(brand_color, 0.55), tuple(max(0, c - 45) for c in brand_color))
    canvas = canvas.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    pad = 64

    head_font = _font("ExtraBold", 62)
    head_lines = _wrap_text(draw, headline, head_font, CANVAS - pad * 2)[:2]
    y = pad + 8
    for line in head_lines:
        draw.text((pad, y), line, font=head_font, fill=WHITE)
        y += 74
    sub_font = _font("Medium", 30)
    for line in _wrap_text(draw, subtext, sub_font, CANVAS - pad * 2)[:1]:
        draw.text((pad, y + 4), line, font=sub_font, fill=_lighten(brand_color, 0.9))
        y += 42

    # 폰 화면을 최대한 크게(하단이 잘려나가며 화면 밖으로 이어지는 연출)
    top = y + 34
    avail_h = CANVAS - top
    src = Image.open(BytesIO(illustration_bytes)).convert("RGB")
    scale = min((CANVAS * 0.62) / src.width, (avail_h * 1.25) / src.height)
    shot = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
    sx = (CANVAS - shot.width) // 2
    _shadow_box(canvas, (sx, top, sx + shot.width, min(CANVAS, top + shot.height)), 40, blur=24)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), shot.size], radius=40, fill=255)
    canvas.paste(shot, (sx, top), mask)

    if page_label:
        lf = _font("SemiBold", 24)
        d2 = ImageDraw.Draw(canvas)
        d2.text((CANVAS - pad - d2.textlength(page_label, font=lf), pad + 8), page_label, font=lf, fill=WHITE)

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


# 2세대 레이아웃 등록(정의가 RENDERERS 딕셔너리보다 아래에 있어 여기서 추가한다)
RENDERERS.update({"editorial": render_editorial, "marker": render_marker, "device": render_device})
