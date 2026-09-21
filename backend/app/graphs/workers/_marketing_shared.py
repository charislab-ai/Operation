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
