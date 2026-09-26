"""조합형 카드 레이아웃 엔진 - 고정된 틀 목록 대신 "구성 요소의 조합"으로 카드를 그린다.

Why: 예전엔 banded/overlay/bold_type/split 같은 완성된 틀을 파이썬에 하드코딩해두고 AI가 그중
하나를 고르기만 했다. 그래서 하루 2회 도는 벤치마킹이 스크랩북·밈·폴라로이드·체크리스트·인용구·
Before/After 등 14종 넘는 실제 인기 틀을 찾아내도(docs/marketing_benchmarks 17개 회차) 코드에
없으니 영원히 쓸 수 없었고, 결과물은 늘 같은 몇 개 틀로만 나왔다(CEO 지적).

이제 AI(비주얼 디자이너)가 배경/사진처리/사진위치/기울기/텍스트패널/강조요소를 직접 조합해서
레이아웃을 "설계"한다. 벤치마킹 리포트에서 본 틀을 조합으로 재현할 수 있고, 새 틀이 발견돼도
코드 수정 없이 바로 쓸 수 있다.
"""

import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter

from app.tools.ai.image.card_renderer import (
    CANVAS,
    DEFAULT_BRAND,
    INK,
    WHITE,
    _crop_to_ratio,
    _fit_or_crop,
    _font,
    _lighten,
    _vertical_gradient,
    _wrap_text,
)

PAPER = (243, 239, 231)
INK_DEEP = (18, 16, 30)
_HEADLINE_SIZE = {"m": 56, "l": 72, "xl": 92}


def _paper_background(size: tuple[int, int], seed: int = 7) -> Image.Image:
    """스크랩북/메모지 느낌의 종이 배경 - 미세한 얼룩을 넣어 단색 플랫함을 없앤다."""
    canvas = Image.new("RGB", size, PAPER)
    rnd = random.Random(seed)
    draw = ImageDraw.Draw(canvas)
    for _ in range(1400):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        shade = rnd.randint(-8, 4)
        draw.point((x, y), fill=tuple(max(0, min(255, PAPER[i] + shade)) for i in range(3)))
    return canvas.filter(ImageFilter.SMOOTH)


def _rounded(img: Image.Image, radius: int) -> tuple[Image.Image, Image.Image]:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
    return img, mask


def _paste_with_shadow(base: Image.Image, img: Image.Image, mask: Image.Image, pos: tuple[int, int]) -> None:
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 110))
    shadow.paste(sh, (pos[0], pos[1] + 12), mask)
    blurred = shadow.filter(ImageFilter.GaussianBlur(20))
    base.alpha_composite(blurred)
    base.paste(img, pos, mask)


def _tape(draw: ImageDraw.ImageDraw, cx: int, cy: int, angle: int, brand: tuple[int, int, int]) -> None:
    """스크랩북 느낌의 마스킹 테이프 조각."""
    w, h = 130, 40
    tape = Image.new("RGBA", (w, h), (*_lighten(brand, 0.6), 190))
    rotated = tape.rotate(angle, expand=True)
    draw._image.alpha_composite(rotated, (cx - rotated.width // 2, cy - rotated.height // 2))


def _place_photo(canvas: Image.Image, photo_bytes: bytes, spec: dict, brand: tuple[int, int, int]) -> tuple[int, int, int, int]:
    """사진을 spec대로 배치하고, 텍스트가 피해야 할 영역(box)을 돌려준다."""
    style = spec.get("photo_style", "full")
    area = spec.get("photo_area", "full")
    tilt = max(-10, min(10, int(spec.get("photo_tilt", 0) or 0)))

    if style == "none" or not photo_bytes:
        return (0, 0, 0, 0)

    if style == "full" or area == "full":
        canvas.paste(_fit_or_crop(photo_bytes, CANVAS, CANVAS, INK_DEEP).convert("RGBA"), (0, 0))
        return (0, 0, CANVAS, CANVAS)

    # 영역별 기본 박스
    boxes = {
        "top": (0, 0, CANVAS, int(CANVAS * 0.56)),
        "bottom": (0, int(CANVAS * 0.44), CANVAS, CANVAS),
        "left": (0, 0, int(CANVAS * 0.52), CANVAS),
        "right": (int(CANVAS * 0.48), 0, CANVAS, CANVAS),
        "center": (int(CANVAS * 0.14), int(CANVAS * 0.18), int(CANVAS * 0.86), int(CANVAS * 0.72)),
    }
    x0, y0, x1, y1 = boxes.get(area, boxes["top"])
    w, h = x1 - x0, y1 - y0

    if style == "strip":
        h = int(CANVAS * 0.3)
        y0 = CANVAS - h - 70 if area != "top" else 70
        y1 = y0 + h

    if style == "circle":
        size = min(w, h)
        img = _crop_to_ratio(photo_bytes, size, size)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([(0, 0), (size, size)], fill=255)
        pos = (x0 + (w - size) // 2, y0 + (h - size) // 2)
        _paste_with_shadow(canvas, img.convert("RGBA"), mask, pos)
        return (pos[0], pos[1], pos[0] + size, pos[1] + size)

    if style == "device":
        # 폰 목업은 크게 띄우고 아래로 흘려보낸다 - 작게 넣으면 배경 여백만 넓어져 초라해 보임
        src = Image.open(BytesIO(photo_bytes)).convert("RGB")
        scale = (CANVAS * 0.66) / src.width
        img = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
        img, mask = _rounded(img, 44)
        top = y0 if area != "center" else y0
        pos = ((CANVAS - img.width) // 2, top)
        _paste_with_shadow(canvas, img.convert("RGBA"), mask, pos)
        return (pos[0], pos[1], pos[0] + img.width, min(CANVAS, pos[1] + img.height))

    if style == "polaroid":
        frame_w = int(min(w, h) * 0.92)
        inner = frame_w - 48
        img = _crop_to_ratio(photo_bytes, inner, inner)
        frame = Image.new("RGB", (frame_w, frame_w + 70), WHITE)
        frame.paste(img, (24, 24))
        if tilt:
            frame = frame.rotate(tilt, expand=True, fillcolor=None, resample=Image.BICUBIC)
        fimg, fmask = _rounded(frame, 8)
        pos = (x0 + (w - fimg.width) // 2, y0 + (h - fimg.height) // 2)
        _paste_with_shadow(canvas, fimg.convert("RGBA"), fmask, pos)
        return (pos[0], pos[1], pos[0] + fimg.width, pos[1] + fimg.height)

    # card (기본) - 둥근 모서리 카드
    img = _fit_or_crop(photo_bytes, w - 40, h - 40, _lighten(brand, 0.8))
    if tilt:
        img = img.rotate(tilt, expand=True, resample=Image.BICUBIC, fillcolor=PAPER)
    img, mask = _rounded(img, 32)
    pos = (x0 + (w - img.width) // 2, y0 + (h - img.height) // 2)
    _paste_with_shadow(canvas, img.convert("RGBA"), mask, pos)
    return (pos[0], pos[1], pos[0] + img.width, pos[1] + img.height)


def render_composed(
    illustration_bytes: bytes,
    headline: str,
    subtext: str,
    product: str,
    page_label: str | None = None,
    brand_color: tuple[int, int, int] = DEFAULT_BRAND,
    spec: dict | None = None,
) -> bytes:
    """AI가 설계한 레이아웃 spec대로 카드를 그린다."""
    spec = spec or {}
    background = spec.get("background", "photo_full")
    text_panel = spec.get("text_panel", "scrim")
    text_position = spec.get("text_position", "bottom")
    accent = spec.get("accent", "none")
    head_size = _HEADLINE_SIZE.get(spec.get("headline_scale", "l"), 72)

    # 1) 배경
    if background == "ink":
        canvas = Image.new("RGB", (CANVAS, CANVAS), INK_DEEP).convert("RGBA")
    elif background == "brand_gradient":
        canvas = _vertical_gradient(
            (CANVAS, CANVAS), _lighten(brand_color, 0.5), tuple(max(0, c - 50) for c in brand_color)
        ).convert("RGBA")
    elif background == "paper":
        canvas = _paper_background((CANVAS, CANVAS)).convert("RGBA")
    elif background == "light":
        canvas = Image.new("RGB", (CANVAS, CANVAS), (250, 249, 247)).convert("RGBA")
    else:  # photo_full
        canvas = Image.new("RGB", (CANVAS, CANVAS), INK_DEEP).convert("RGBA")

    # 2) 사진
    photo_box = _place_photo(canvas, illustration_bytes, spec, brand_color)
    draw = ImageDraw.Draw(canvas)

    if background == "paper" and spec.get("photo_style") in ("polaroid", "card") and photo_box[2]:
        _tape(draw, (photo_box[0] + photo_box[2]) // 2, photo_box[1] + 6, 8, brand_color)

    dark_bg = background in ("ink", "brand_gradient") or (
        background == "photo_full" and text_panel == "scrim"
    )
    text_color = WHITE if dark_bg else INK_DEEP
    sub_color = (200, 198, 215) if dark_bg else (110, 108, 125)

    # 3) 텍스트 영역 계산
    pad = 64
    max_text_w = CANVAS - pad * 2
    if spec.get("photo_area") in ("left", "right") and spec.get("photo_style") not in ("none", "full"):
        max_text_w = int(CANVAS * 0.44) - pad
    head_font = _font("Black" if head_size >= 92 else "ExtraBold", head_size)
    sub_font = _font("Medium", 30)
    head_lines = _wrap_text(draw, headline, head_font, max_text_w)[:3]
    sub_lines = _wrap_text(draw, subtext, sub_font, max_text_w)[:2] if subtext else []
    line_h = int(head_size * 1.18)
    block_h = len(head_lines) * line_h + (len(sub_lines) * 42 + 14 if sub_lines else 0)

    tx = pad if spec.get("photo_area") != "left" else int(CANVAS * 0.56)
    if text_position == "top":
        # 상단 제품 뱃지 아래에서 시작(겹침 방지). number/quote 장식은 제목 "위쪽"에 그려지므로
        # 그만큼 더 내려야 뱃지를 덮지 않는다(브랜드 QA가 실물 카드에서 잡아낸 겹침 사고).
        ty = pad + 62 + (110 if accent in ("number", "quote") else 0)
    elif text_position == "center":
        ty = (CANVAS - block_h) // 2
    else:
        ty = CANVAS - pad - block_h - (40 if page_label else 0)

    # 4) 텍스트 패널
    if text_panel == "white_card":
        box = (tx - 36, ty - 40, min(CANVAS - pad + 36, tx + max_text_w + 36), ty + block_h + 40)
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [(box[0], box[1] + 12), (box[2], box[3] + 12)], radius=32, fill=(0, 0, 0, 95)
        )
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle([(box[0], box[1]), (box[2], box[3])], radius=32, fill=WHITE)
        text_color, sub_color = INK_DEEP, (110, 108, 125)
    elif text_panel == "note":
        box = (tx - 30, ty - 34, min(CANVAS - pad + 30, tx + max_text_w + 30), ty + block_h + 34)
        draw.rounded_rectangle([box[0], box[1], box[2], box[3]], radius=10, fill=(255, 249, 214))
        text_color, sub_color = INK_DEEP, (120, 110, 80)
    elif text_panel == "scrim" and background == "photo_full":
        scrim_top = max(0, ty - 90)
        grad = Image.new("L", (1, CANVAS - scrim_top))
        for i in range(CANVAS - scrim_top):
            grad.putpixel((0, i), int(240 * (i / max(1, CANVAS - scrim_top)) ** 1.3))
        grad = grad.resize((CANVAS, CANVAS - scrim_top))
        dark = Image.new("RGBA", (CANVAS, CANVAS - scrim_top), (8, 6, 16, 255))
        canvas.paste(dark, (0, scrim_top), grad)
        draw = ImageDraw.Draw(canvas)

    # 5) 강조 요소 + 텍스트
    if accent == "quote":
        qf = _font("Black", 130)
        draw.text((tx - 8, ty - 128), "“", font=qf, fill=brand_color)
    if accent == "number" and page_label:
        n = page_label.split("/")[0]
        nf = _font("Black", 64)
        draw.ellipse([(tx, ty - 108), (tx + 84, ty - 24)], fill=brand_color)
        nw = draw.textlength(n, font=nf)
        draw.text((tx + 42 - nw / 2, ty - 100), n, font=nf, fill=WHITE)

    y = ty
    for line in head_lines:
        if accent == "marker":
            w = draw.textlength(line, font=head_font)
            draw.rounded_rectangle(
                [(tx - 8, y + int(head_size * 0.82)), (tx + w + 12, y + int(head_size * 1.16))],
                radius=8,
                fill=brand_color,
            )
        draw.text((tx, y), line, font=head_font, fill=text_color)
        if accent == "underline":
            w = draw.textlength(line, font=head_font)
            draw.rounded_rectangle(
                [(tx, y + int(head_size * 1.05)), (tx + w, y + int(head_size * 1.05) + 8)], radius=4, fill=brand_color
            )
        y += line_h

    y += 14
    for line in sub_lines:
        if accent == "checklist":
            draw.rounded_rectangle([(tx, y + 4), (tx + 26, y + 30)], radius=6, outline=brand_color, width=3)
            draw.line([(tx + 6, y + 17), (tx + 12, y + 24), (tx + 21, y + 9)], fill=brand_color, width=4)
            draw.text((tx + 40, y), line, font=sub_font, fill=sub_color)
        else:
            draw.text((tx, y), line, font=sub_font, fill=sub_color)
        y += 42

    # 6) 제품 뱃지 + 페이지
    bf = _font("Bold", 24)
    # 어두운 배경(잉크/브랜드 그라디언트)에선 브랜드 컬러를 밝힌 색이 배경과 거의 같은 색이라
    # 뱃지가 안 보였다(실측) - 어두운 배경에선 흰색으로 찍는다.
    draw.text((pad, pad), product.upper(), font=bf, fill=WHITE if dark_bg else brand_color)
    if page_label:
        lf = _font("SemiBold", 24)
        lw = draw.textlength(page_label, font=lf)
        draw.text((CANVAS - pad - lw, pad), page_label, font=lf, fill=sub_color)

    buf = BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
