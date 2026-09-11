import base64
import re

import httpx

from app.config import settings

# 마케팅 벤치마킹 리포트(클라우드 루틴이 하루 2회 GitHub에 직접 커밋)를 읽는 공용 클라이언트.
# app/api/marketing.py(웹 조회 화면)와 app/graphs/workers/marketing_worker.py(콘텐츠 생성 시
# 실제로 반영) 양쪽에서 재사용한다.
GITHUB_API_BASE = "https://api.github.com"
BENCHMARKS_PATH = "docs/marketing_benchmarks"
BENCHMARK_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-UTC\.md$")


def _github_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def list_benchmark_filenames() -> list[str]:
    """docs/marketing_benchmarks/ 안의 리포트 파일명을 최신순으로 반환. 실패하면 빈 리스트."""
    if not settings.github_token:
        return []
    url = f"{GITHUB_API_BASE}/repos/{settings.github_repo}/contents/{BENCHMARKS_PATH}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_github_headers())
    except httpx.HTTPError:
        return []
    if resp.status_code != 200:
        return []
    names = [e.get("name", "") for e in resp.json() if BENCHMARK_FILENAME_RE.match(e.get("name", ""))]
    return sorted(names, reverse=True)


async def fetch_benchmark_content(filename: str) -> str | None:
    """리포트 원문(마크다운)을 반환. 실패하면 None."""
    if not settings.github_token or not BENCHMARK_FILENAME_RE.match(filename):
        return None
    url = f"{GITHUB_API_BASE}/repos/{settings.github_repo}/contents/{BENCHMARKS_PATH}/{filename}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_github_headers())
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return base64.b64decode(resp.json()["content"]).decode("utf-8")


async def fetch_latest_benchmarks(limit: int = 2) -> list[str]:
    """가장 최근 리포트 N개의 원문을 반환(마케팅 콘텐츠 생성 시 참고용). 실패/미설정 시 빈 리스트."""
    filenames = await list_benchmark_filenames()
    contents = []
    for name in filenames[:limit]:
        content = await fetch_benchmark_content(name)
        if content:
            contents.append(content)
    return contents
