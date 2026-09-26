"""벤치마킹 리포트에서 새로 발견된 카드 틀을 라이브러리에 자동 등록한다.

닫힌 고리: 하루 2회 도는 벤치마킹 루틴이 인스타그램에서 인기 틀을 찾으면 리포트 markdown에
```layout-spec 블록으로 규격화해 적어두고, 서버가 그 블록을 읽어 layout_library에 넣는다.
그러면 비주얼 디자이너가 다음 콘텐츠부터 그 틀을 골라 쓰거나 다른 틀과 조합할 수 있다.
예전엔 리포트가 14종 넘는 틀을 찾아내도 코드에 없으면 영원히 못 쓰는 구조였다(CEO 지적).
"""

import json
import logging
import re

from app.db.supabase_client import get_supabase
from app.tools.github_benchmarks import fetch_latest_benchmarks

logger = logging.getLogger(__name__)

_BLOCK_RE = re.compile(r"```layout-spec\s*(\{.*?\}|\[.*?\])\s*```", re.S)

_ALLOWED = {
    "background": {"photo_full", "ink", "brand_gradient", "paper", "light"},
    "photo_style": {"full", "card", "polaroid", "circle", "strip", "device", "none"},
    "photo_area": {"full", "top", "bottom", "left", "right", "center"},
    "text_panel": {"scrim", "white_card", "plain", "note"},
    "text_position": {"top", "center", "bottom"},
    "headline_scale": {"m", "l", "xl"},
    "accent": {"none", "marker", "underline", "number", "quote", "checklist"},
}


def _valid_spec(spec: dict) -> bool:
    """렌더러가 해석할 수 없는 값이 들어오면 카드가 깨지므로 허용값만 통과시킨다."""
    if not isinstance(spec, dict) or "background" not in spec or "photo_style" not in spec:
        return False
    for key, allowed in _ALLOWED.items():
        if key in spec and spec[key] not in allowed:
            return False
    tilt = spec.get("photo_tilt", 0)
    return isinstance(tilt, int) and -10 <= tilt <= 10


def _extract(markdown: str) -> list[dict]:
    found: list[dict] = []
    for raw in _BLOCK_RE.findall(markdown or ""):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in parsed if isinstance(parsed, list) else [parsed]:
            if isinstance(item, dict) and item.get("name") and _valid_spec(item.get("spec") or {}):
                found.append(item)
    return found


async def sync_layouts_from_benchmarks(limit: int = 3) -> int:
    """최근 벤치마킹 리포트에서 새 틀을 찾아 라이브러리에 추가한다. 추가된 개수를 반환."""
    reports = await fetch_latest_benchmarks(limit=limit)
    if not reports:
        return 0

    supabase = get_supabase()
    existing = {r["name"] for r in supabase.table("layout_library").select("name").execute().data}
    added = 0
    for markdown in reports:
        for item in _extract(markdown):
            if item["name"] in existing:
                continue
            supabase.table("layout_library").insert(
                {
                    "name": item["name"],
                    "when_to_use": item.get("when_to_use") or "(설명 없음)",
                    "spec": item["spec"],
                    "source": item.get("source") or "마케팅 벤치마킹 자동 등록",
                }
            ).execute()
            existing.add(item["name"])
            added += 1
            logger.info("새 카드 틀 등록: %s", item["name"])
    return added
