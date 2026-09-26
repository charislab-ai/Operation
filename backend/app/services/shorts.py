"""쇼츠/릴스(1080x1920 세로 영상) 생성 - AI 영상 생성 없이 이미 만든 이미지를 재활용한다.

Why: 카드뉴스/인스타툰을 만들 때 이미지는 이미 다 있으므로, 같은 소재로 영상까지 뽑으면
추가 AI 비용이 0인데 노출 채널이 하나 더 생긴다(릴스/쇼츠는 피드보다 도달이 넓다).
벤치마킹 리포트(2026-09-26 "릴스툰 확장 옵션")가 제안한 것을 그대로 구현한 것.

두 가지 입력을 지원한다:
  1) 게시물 이미지들 → 켄번즈 줌 + 크로스페이드로 조립 (render_from_images)
  2) CEO가 올린 앱 화면 녹화 → 9:16으로 맞추고 브랜드 헤더/자막/CTA를 얹음 (render_from_video)

오디오는 일부러 넣지 않는다 - 릴스/쇼츠는 앱 내 인기 오디오를 붙이는 쪽이 도달에 유리하고,
외부 음원은 저작권 차단 위험이 있다. 게시할 때 앱에서 고르는 게 낫다.
"""

import logging
import math
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.db.supabase_client import get_supabase
from app.tools.ai.image.card_renderer import DEFAULT_BRAND, FONTS_DIR

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 30
CUT_SECONDS = 2.4
FADE_SECONDS = 0.35
MAX_RECORDING_SECONDS = 30  # 쇼츠 권장 길이 - 더 긴 녹화는 앞부분만 쓴다
INK = (13, 16, 23)
VIDEO_BUCKET = "marketing-images"  # 이미지와 같은 공개 버킷(메타가 URL로 받아가야 함)


class ShortsError(Exception):
    """영상 생성 실패 - 게시물 자체는 유효하므로 호출부에서 조용히 넘길 수 있게 별도 예외."""


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / f"Pretendard-{weight}.otf"), size)


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - 배포 환경엔 requirements로 포함됨
        raise ShortsError("ffmpeg 바이너리(imageio-ffmpeg)가 설치되지 않았습니다") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", (1, H))
    for y in range(H):
        k = y / (H - 1)
        base.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return base.resize((W, H)).convert("RGBA")


def _lighten(rgb: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def _brand_overlay(product: str, subtitle: str, brand: tuple[int, int, int], progress: float | None) -> Image.Image:
    """상단 브랜드 바 + 하단 자막/CTA - 이미지든 녹화든 같은 껍데기를 씌워 톤을 통일한다."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    d.rounded_rectangle([48, 76, 48 + 84, 76 + 84], radius=24, fill=brand)
    d.text((64, 96), product[:2].upper(), font=_font("Black", 40), fill=(255, 255, 255))
    d.text((156, 88), product, font=_font("ExtraBold", 42), fill=INK)
    d.text((156, 138), "iOS 무료 · 지금 다운로드", font=_font("Medium", 26), fill=(72, 84, 116))

    if subtitle:
        f = _font("SemiBold", 34)
        tw = d.textlength(subtitle, font=f)
        bw, bh = tw + 76, 84
        x, y = (W - bw) / 2, H - 330
        d.rounded_rectangle([x, y, x + bw, y + bh], radius=22, fill=(*INK, 232))
        d.text((x + 38, y + 22), subtitle, font=f, fill=(255, 255, 255))

    cta = "프로필 링크에서 다운로드"
    cf = _font("Bold", 40)
    cw = d.textlength(cta, font=cf)
    d.rounded_rectangle([(W - cw) / 2 - 48, H - 210, (W + cw) / 2 + 48, H - 118], radius=46, fill=INK)
    d.text(((W - cw) / 2, H - 190), cta, font=cf, fill=(255, 255, 255))

    if progress is not None:
        bar_y = H - 76
        d.rounded_rectangle([64, bar_y, W - 64, bar_y + 10], radius=5, fill=(255, 255, 255, 190))
        d.rounded_rectangle([64, bar_y, 64 + int((W - 128) * progress), bar_y + 10], radius=5, fill=brand)
    return layer


def _encode(frames_dir: Path, out_path: Path) -> None:
    subprocess.run(
        [
            _ffmpeg(), "-y", "-framerate", str(FPS), "-i", str(frames_dir / "f%05d.png"),
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out_path),
        ],
        check=True, capture_output=True,
    )


def render_from_images(
    image_urls: list[str],
    product: str,
    brand: tuple[int, int, int] = DEFAULT_BRAND,
) -> bytes:
    """게시물 이미지(카드뉴스/인스타툰 컷)를 세로 영상으로 조립한다.

    카드 안에 이미 자막/말풍선이 들어 있으므로 영상 쪽 자막은 얹지 않는다(중복되면 지저분함) -
    상단 브랜드 바, 하단 CTA, 진행바만 추가한다."""
    if not image_urls:
        raise ShortsError("영상으로 만들 이미지가 없습니다")

    images: list[Image.Image] = []
    with httpx.Client(timeout=30) as client:
        for url in image_urls[:6]:  # 6장이면 15초 내외 - 쇼츠 권장 길이를 넘기지 않는다
            resp = client.get(url)
            if resp.status_code == 200:
                from io import BytesIO

                images.append(Image.open(BytesIO(resp.content)).convert("RGB"))
    if not images:
        raise ShortsError("이미지를 불러오지 못했습니다")

    background = _gradient(_lighten(brand, 0.90), _lighten(brand, 0.66))
    per_cut, fade = int(CUT_SECONDS * FPS), int(FADE_SECONDS * FPS)
    total = per_cut * len(images)

    def compose(img: Image.Image, zoom: float, progress: float) -> Image.Image:
        frame = background.copy()
        tw = int(W * zoom)
        th = int(img.height * tw / img.width)
        scaled = img.resize((tw, th), Image.LANCZOS)
        x, y = (W - tw) // 2, (H - th) // 2 - 40
        shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [x + 10, y + 22, x + tw - 10, y + th + 22], radius=28, fill=(20, 30, 60, 110)
        )
        frame.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(26)))
        mask = Image.new("L", scaled.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([(0, 0), scaled.size], radius=28, fill=255)
        frame.paste(scaled, (x, y), mask)
        frame.alpha_composite(_brand_overlay(product, "", brand, progress))
        return frame

    tmp = Path(tempfile.mkdtemp(prefix="shorts_"))
    try:
        frames = tmp / "frames"
        frames.mkdir()
        idx = 0
        for i, img in enumerate(images):
            for f in range(per_cut):
                t = f / per_cut
                frame = compose(img, 0.90 + 0.05 * t, idx / total)
                if f >= per_cut - fade and i + 1 < len(images):
                    k = (f - (per_cut - fade)) / fade
                    frame = Image.blend(frame, compose(images[i + 1], 0.90, idx / total), k)
                frame.convert("RGB").save(frames / f"f{idx:05d}.png")
                idx += 1
        out = tmp / "shorts.mp4"
        _encode(frames, out)
        return out.read_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_from_video(
    video_bytes: bytes,
    product: str,
    subtitle: str = "",
    brand: tuple[int, int, int] = DEFAULT_BRAND,
    seconds: int = MAX_RECORDING_SECONDS,
) -> bytes:
    """CEO가 올린 앱 화면 녹화를 쇼츠로 만든다.

    녹화본을 9:16 캔버스에 맞추고(비율이 달라도 잘리지 않게 패딩), 브랜드 헤더/자막/CTA
    오버레이를 얹는다. 실제 쓰는 화면이 앱 홍보에서 가장 설득력이 높아서 이 경로를 따로 둔다.
    """
    tmp = Path(tempfile.mkdtemp(prefix="shorts_rec_"))
    try:
        src = tmp / "src.mp4"
        src.write_bytes(video_bytes)
        overlay_path = tmp / "overlay.png"
        _brand_overlay(product, subtitle, brand, None).save(overlay_path)
        out = tmp / "shorts.mp4"
        # scale: 9:16 안쪽에 맞추고(비율 유지) 남는 부분은 브랜드 톤 배경으로 채운다
        pad_color = "0x%02X%02X%02X" % _lighten(brand, 0.86)
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={pad_color},setsar=1"
        )
        subprocess.run(
            [
                _ffmpeg(), "-y", "-t", str(seconds), "-i", str(src), "-i", str(overlay_path),
                "-filter_complex", f"[0:v]{vf}[bg];[bg][1:v]overlay=0:0",
                "-r", str(FPS), "-an",  # 오디오 제거(앱에서 인기 오디오를 붙이는 게 낫다)
                "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out),
            ],
            check=True, capture_output=True,
        )
        return out.read_bytes()
    except subprocess.CalledProcessError as exc:
        raise ShortsError(f"영상 변환 실패: {exc.stderr.decode()[:300]}") from exc
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def upload_video(video_bytes: bytes) -> str:
    """완성된 영상을 공개 버킷에 올리고 URL을 돌려준다(메타가 URL로 받아가므로 공개 필수)."""
    path = f"{uuid.uuid4()}.mp4"
    bucket = get_supabase().storage.from_(VIDEO_BUCKET)
    bucket.upload(path, video_bytes, {"content-type": "video/mp4"})
    return bucket.get_public_url(path)
