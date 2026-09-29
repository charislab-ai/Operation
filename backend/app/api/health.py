import subprocess

from fastapi import APIRouter

# 민감한 내용이 든 대표 테이블만 확인한다(전수 조회는 헬스체크를 느리게 만든다)
_RLS_CHECK_TABLES = ("directives", "approvals", "employees", "products", "ai_usage_log")

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


def _claude_cli_status() -> str:
    """Claude Code CLI가 이 서버에서 실행 가능한지 - LLM 호출을 구독으로 돌리는 경로라
    없으면 조용히 API 종량제로 폴백해버려서 눈치채기 어렵다."""
    from app.config import settings

    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return f"실행 실패: {out.stderr[:100]}"
        auth = "구독 토큰 있음" if settings.claude_code_oauth_token else "⚠️ 토큰 없음(API 종량제로 동작)"
        return f"{out.stdout.strip()} · {auth}"
    except Exception as exc:
        return f"사용 불가: {exc}"


def _rls_status() -> str:
    """RLS(행 수준 보안)가 꺼진 공개 테이블이 있는지 확인한다.

    Why: 이 프로젝트는 "모든 테이블 RLS ON + 정책 없음, 백엔드만 service_role로 접근"이
    원칙인데(0001_init.sql), 새 테이블을 만들면서 RLS 켜는 걸 빠뜨리면 **프로젝트 URL과
    공개 키만으로 누구나 읽고 지울 수 있는 상태**가 된다(실제로 발생해 Supabase 보안 경고를
    받음 - employees/brand_identity/account_snapshots 3개). 눈에 띄게 노출해 재발을 막는다.
    """
    try:
        import httpx

        from app.config import settings

        # 공개 키로 각 테이블을 실제로 읽어본다 - 행이 돌아오면 외부에 노출된 것이다.
        anon = settings.supabase_anon_key
        if not anon:
            return "확인 불가(anon 키 미설정)"
        headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
        exposed = []
        for table in _RLS_CHECK_TABLES:
            r = httpx.get(
                f"{settings.supabase_url}/rest/v1/{table}?select=*&limit=1", headers=headers, timeout=8
            )
            if r.status_code == 200 and isinstance(r.json(), list) and r.json():
                exposed.append(table)
        return "모든 테이블 차단됨" if not exposed else f"⚠️ 외부에 노출된 테이블: {', '.join(exposed)}"
    except Exception as exc:
        return f"확인 실패: {exc}"


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "ffmpeg": _ffmpeg_status(),
        "claude_cli": _claude_cli_status(),
        "rls": _rls_status(),
    }
