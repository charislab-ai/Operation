"""마케팅 팀(MarketingDirector/ContentStrategist/VisualDesigner)이 공유하는 헬퍼.
로직은 기존 단일 MarketingWorker에서 그대로 옮겨온 것 - 변경 없음."""

from app.db.supabase_client import get_supabase
from app.graphs.state import OSState

# LLM이 "SnapTale"처럼 예전 이름으로 부를 수 있어 실제 키로 정규화
PRODUCT_ALIASES = {"snaptale": "SNAPTAIL", "snap tale": "SNAPTAIL", "touchrush": "터치러쉬"}


def canonical_product(product: str) -> str:
    return PRODUCT_ALIASES.get(product.strip().lower(), product)


def original_ceo_text(state: OSState) -> str:
    """마케팅 디렉터가 slide_topics로 요약하기 전 CEO 원문(+보완 사유)을 그대로 반환한다.

    Why: 콘텐츠 전략가/비주얼 디자이너는 지금까지 디렉터가 distillation한 slide_topics만
    보고 작업했는데, CEO가 원문에 적은 구체적 시각/카피 요청(색상, 특정 요소, 스타일 등)이
    디렉터의 요약 과정에서 누락될 수 있다는 게 실측(CEO 피드백)으로 확인됐다 - 전략가/디자이너
    프롬프트에도 이 원문을 같이 넘겨서 구체적 요청을 직접 볼 수 있게 한다."""
    text = state.get("worker_briefs", {}).get("marketing") or state["ceo_directive"]
    note = state.get("revision_notes", {}).get("marketing")
    return f"{text}\n\n[CEO 보완 요청 사유] {note}" if note else text


def fetch_products() -> dict[str, dict]:
    """앱관리 화면(products 테이블)에서 스토어 링크/브랜드 컬러/설명을 가져온다.

    예전엔 이 값들이 코드에 하드코딩돼 있었음(브랜드 컬러는 미확인 추정치였음) - 이제 CEO가
    앱관리 화면에서 직접 수정하면 다음 마케팅 콘텐츠 생성부터 바로 반영된다.
    """
    rows = get_supabase().table("products").select("*").execute().data
    return {r["name"]: r for r in rows}


def hex_to_rgb(hex_color: str | None) -> tuple[int, int, int] | None:
    if not hex_color:
        return None
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except ValueError:
        return None


def append_download_cta(caption: str, product: str, channel: str, products_by_name: dict[str, dict]) -> str:
    if channel == "instagram":
        # 인스타그램은 캡션 링크가 클릭되지 않아 프로필(bio) 링크를 안내한다
        return f"{caption}\n\n👉 앱 다운로드는 프로필 링크를 확인해주세요"

    row = products_by_name.get(canonical_product(product))
    if not row:
        return caption  # 앱관리에 등록되지 않은 제품이면 그대로 둠

    parts = []
    if row.get("ios_url"):
        parts.append(f"iOS: {row['ios_url']}")
    if row.get("android_url"):
        parts.append(f"Android: {row['android_url']}")
    if not parts:
        return caption
    return f"{caption}\n\n👉 지금 다운로드\n" + "\n".join(parts)


# ---------------------------------------------------------------------------
# 전문가별 자료 배분 - 같은 자료 뭉치를 전원에게 통째로 주던 걸 역할별로 잘라서 준다.
# Why: 실측(thread b1c46ad7)에서 전략가 47,892 / 디자이너 52,255 / 디렉터 41,082 입력 토큰이
# 나왔는데, 대부분이 "벤치마킹 리포트 2개 전문"을 세 명이 각자 통째로 받은 탓이었다. 캡션 톤
# 인사이트는 디자이너에게 쓸모없고 레이아웃 인사이트는 카피라이터에게 쓸모없다. 역할별로
# 필요한 절(##/### 섹션)만 뽑아 주면 사람이 늘어도 총비용은 오히려 줄고, 각자 자기 일에
# 해당하는 지침만 보게 되어 지침을 흘리는 문제도 줄어든다.
# ---------------------------------------------------------------------------

_ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "copy": ("카피", "문구", "헤드라인", "훅", "후킹", "톤", "말투", "대사", "인스타툰", "스토리텔링", "공감"),
    "caption": ("캡션", "해시태그", "태그", "cta", "댓글", "저장", "공유", "알고리즘", "도달", "스토리", "릴스"),
    "photo": ("사진", "이미지", "영상", "장면", "구도", "촬영", "before", "after", "비포", "ugc", "인물", "썸네일"),
    "layout": ("레이아웃", "틀", "카드", "캐러셀", "타이포", "폰트", "컬러", "색", "디자인", "슬라이드", "그리드"),
    # 디렉터는 "장 구성을 어떻게 짜는가"에 해당하는 절만 본다(문구/사진/조판 디테일은 담당자 몫).
    "structure": ("구성", "구조", "캐러셀", "컷", "기승전결", "후킹", "훅", "에피소드", "포맷", "패턴"),
}

_MAX_SLICE_CHARS = 6000


def _sections(report: str) -> list[tuple[str, str]]:
    """마크다운 리포트를 "## 제목" 단위 섹션으로 쪼갠다(하위 ### 는 해당 섹션에 포함)."""
    sections: list[tuple[str, str]] = []
    title, buf = "머리말", []
    for line in report.splitlines():
        if line.startswith("## "):
            if buf:
                sections.append((title, "\n".join(buf)))
            title, buf = line[3:].strip(), [line]
        else:
            buf.append(line)
    if buf:
        sections.append((title, "\n".join(buf)))
    return sections


def benchmark_slice(reports: list[str], role: str) -> str:
    """벤치마킹 리포트에서 이 역할에 해당하는 섹션만 모아 돌려준다.

    role: copy | caption | photo | layout. 매칭되는 섹션이 하나도 없으면(리포트 제목 양식이
    바뀐 경우 등) 빈 문자열이 아니라 각 리포트의 "적용할 아이디어" 절이나 앞부분을 조금
    돌려준다 - 자료를 아예 못 보는 것보다는 낫다."""
    keywords = _ROLE_KEYWORDS.get(role, ())
    picked: list[str] = []
    fallback: list[str] = []
    for report in reports:
        for title, body in _sections(report):
            lowered = f"{title}\n{body[:400]}".lower()
            if any(k in lowered for k in keywords):
                picked.append(body)
            elif "적용" in title:
                fallback.append(body)
    chosen = picked or fallback or [r[:1500] for r in reports]
    out: list[str] = []
    used = 0
    for body in chosen:
        if used + len(body) > _MAX_SLICE_CHARS:
            out.append(body[: max(0, _MAX_SLICE_CHARS - used)])
            break
        out.append(body)
        used += len(body)
    return "\n\n---\n\n".join(out)


def brand_book(product_row: dict | None) -> str:
    """제품별 브랜드북(톤/타깃/핵심 메시지/금지 표현) - 앱관리 화면에서 CEO가 정해둔 값.

    Why 에이전트가 아니라 자산인가: 브랜드 톤은 매번 새로 지어내는 게 아니라 지키는 것이라,
    LLM이 회차마다 새로 정하면 일관성이 무너진다. 한 번 정해두고 전원이 같은 문서를 본다."""
    if not product_row:
        return ""
    lines = [f"[브랜드북 - {product_row.get('name', '')}]"]
    for label, key in (
        ("제품 설명", "description"),
        ("톤앤보이스", "tone_of_voice"),
        ("핵심 타깃", "target_audience"),
        ("핵심 메시지", "key_messages"),
        ("쓰면 안 되는 표현", "banned_words"),
    ):
        value = (product_row.get(key) or "").strip()
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines) if len(lines) > 1 else ""


_EMPLOYEE_CACHE: dict[str, tuple[float, list[dict]]] = {}
_EMPLOYEE_TTL_SECONDS = 60


def fetch_employees(force: bool = False) -> list[dict]:
    """직원 명단(이름/직함/상태). 이름 기반 지목 라우팅과 프롬프트의 자기소개에 쓴다.

    노드마다 여러 번 조회되므로 60초 캐시를 둔다 - CEO가 이름을 바꾸면 최대 1분 뒤부터
    새 이름으로 불러도 알아듣는다(즉시 반영이 필요하면 force=True)."""
    import time

    cached = _EMPLOYEE_CACHE.get("all")
    if not force and cached and time.time() - cached[0] < _EMPLOYEE_TTL_SECONDS:
        return cached[1]
    rows = get_supabase().table("employees").select("*").order("sort_order").execute().data
    _EMPLOYEE_CACHE["all"] = (time.time(), rows)
    return rows


def employee_of(agent_key: str) -> dict:
    return next((e for e in fetch_employees() if e["agent_key"] == agent_key), {})


def detect_addressee(text: str) -> dict | None:
    """지시문에서 직원 이름을 찾아 "누구에게 내린 지시인지" 알아낸다.

    CEO가 "민지야, 카피만 다시 써줘"처럼 이름을 부르면 그 직원만 자기 지시로 받아들이게 하기
    위한 것(app/graphs/supervisor.py에서 부서 라우팅에도 쓰임). 이름이 길수록 구체적이므로
    여러 개가 걸리면 가장 긴 이름을 택한다. 한 글자 이름은 오탐이 많아 무시한다."""
    if not text:
        return None
    matches = [
        e for e in fetch_employees() if len(e.get("name", "")) >= 2 and e["name"] in text
    ]
    if not matches:
        return None
    return max(matches, key=lambda e: len(e["name"]))


def addressing_note(state: OSState, agent_key: str) -> str:
    """이 지시가 특정 직원을 지목한 것인지 알려주는 문구.

    지목된 본인에게는 "당신에게 직접 내려온 지시"라고 알려 원문을 최우선으로 따르게 하고,
    나머지에게는 "다른 직원에게 내려간 지시"라고 알려 엉뚱하게 휘둘리지 않게 한다. 지시문
    원문(보완 사유 포함)에서 매번 다시 찾으므로, 보완 때 새로 부른 이름도 그대로 적용된다."""
    target = detect_addressee(original_ceo_text(state))
    if not target:
        return ""
    if target["agent_key"] == agent_key:
        return (
            f"\n\n[지목] CEO가 이번 지시에서 당신({target['name']} {target['title']})을 직접 "
            "지목했습니다. 아래 CEO 원문의 요구를 당신 담당 영역에서 최우선으로 반영하세요."
        )
    return (
        f"\n\n[참고] 이번 지시는 {target['name']}({target['title']})에게 내려간 것입니다. "
        "당신 담당 영역은 기존 방향을 유지하고, 일관성만 맞춰주세요."
    )
