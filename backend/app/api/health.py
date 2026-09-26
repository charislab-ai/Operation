import subprocess

from fastapi import APIRouter

router = APIRouter(tags=["health"])


def _ffmpeg_status() -> str:
    """쇼츠 렌더링에 쓰는 ffmpeg이 이 서버에서 실제로 실행되는지 확인한다.

    Why: 영상 생성은 실패해도 게시물 자체는 진행되도록 조용히 넘기게 설계했기 때문에
    (app/services/shorts.py), 바이너리가 없으면 "쇼츠가 그냥 안 나오는" 상태를 한참 모른다.
    배포 직후 여기서 한 번 눈으로 확인할 수 있게 노출한다.
    """
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
        return out.stdout.splitlines()[0] if out.returncode == 0 else f"실행 실패: {out.stderr[:120]}"
    except Exception as exc:
        return f"사용 불가: {exc}"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "ffmpeg": _ffmpeg_status()}
