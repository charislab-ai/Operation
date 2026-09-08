import httpx
from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import MarketingPost
from app.graphs.state import OSState
from app.tools.ai.image.card_composer import compose_marketing_card
from app.tools.ai.image.storage import upload_marketing_image
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.workers.rag_worker import rag_search

llm = get_llm()

# LLM이 "SnapTale"처럼 예전 이름으로 부를 수 있어 실제 키로 정규화
PRODUCT_ALIASES = {"snaptale": "SNAPTAIL", "snap tale": "SNAPTAIL", "touchrush": "터치러쉬"}


def _canonical_product(product: str) -> str:
    return PRODUCT_ALIASES.get(product.strip().lower(), product)


def _fetch_products() -> dict[str, dict]:
    """앱관리 화면(products 테이블)에서 스토어 링크/브랜드 컬러/설명을 가져온다.

    예전엔 이 값들이 코드에 하드코딩돼 있었음(브랜드 컬러는 미확인 추정치였음) - 이제 CEO가
    앱관리 화면에서 직접 수정하면 다음 마케팅 콘텐츠 생성부터 바로 반영된다.
    """
    rows = get_supabase().table("products").select("*").execute().data
    return {r["name"]: r for r in rows}


def _hex_to_rgb(hex_color: str | None) -> tuple[int, int, int] | None:
    if not hex_color:
        return None
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))
    except ValueError:
        return None


SYSTEM_PROMPT = """당신은 CharisLab의 마케팅(CMO) 에이전트입니다. CEO의 지시와 (있다면) 제품 특징 문서를
참고해서 홍보할 제품(product), 게시할 채널(channel: instagram|facebook|tiktok|threads), 게시물
전체 캡션(caption), 카드뉴스 슬라이드 목록(slides, 3~5장)을 만드세요. 채널이 명시되지 않으면 지시
맥락상 가장 적합한 채널 하나를 고르세요. 제품 특징 문서가 있으면 막연한 감성 문구 대신 실제 기능이
드러나는 구체적인 문구를 우선하세요.

슬라이드 구성: 1번은 후킹 헤드라인, 중간 슬라이드들은 기능/베네핏을 하나씩, 마지막은 CTA로
구성하세요(예: "지금 다운로드하고 시작하세요"). 캡션에는 다운로드 링크를 직접 쓰지 마세요(별도로
붙습니다). **매번 문구와 구성을 다르게** 써서 같은 지시라도 항상 다른 결과물이 나오게 하세요.

이미지 프롬프트 작성 규칙(슬라이드마다):
- 컬러풀하고 실사에 가까운 사진 스타일, 너무 매끈한 스톡사진 느낌보다 살짝 캐주얼한 스냅샷 느낌
- **조명을 매번 다양하게 명시**하세요 — 낮의 밝은 자연광, 실내 형광등/백색 조명, 흐린 날 부드러운
  빛 등으로 상황에 맞게 다양화하고, 노을/골든아워처럼 화면 전체가 주황빛으로 물드는 조명은
  지시에서 저녁·노을을 명시하지 않는 한 쓰지 마세요(실측으로 계속 누렇게 나오는 문제 확인됨) —
  "natural bright daylight, neutral white balance" 같은 문구로 색온도를 명시적으로 지정하세요
- 인물 사진일 경우 "wide shot, full body or upper body clearly visible with headroom above the
  head, not cropped tightly" 처럼 머리 위 여백을 확보하라고 명시하세요(머리가 잘리는 문제 확인됨)
- **등장인물은 반드시 한국인(Korean people)으로 명시**하세요 — "Korean family"/"Korean
  friends"/"Korean office coworkers" 등으로 구체적으로 적으세요
- 제품 특징 문서에 다양한 사용 시나리오(가족/친구/취미/일상/직장 등)가 언급돼 있다면, 지시에 특정
  장면이 없는 한 매번 같은 장면(예: 가족)으로만 고정하지 말고 슬라이드마다 다른 장면을 골라 폭넓은
  사용 사례를 보여주세요
- 텍스트/로고는 이미지에 넣지 말라고 명시하세요(헤드라인/보조문구는 별도로 합성됩니다)

**실제 앱 스크린샷 활용**: 아래에 등록된 실제 앱 스크린샷 목록이 주어지면, 그중 이번에 만들 제품과
일치하고 슬라이드 내용과 맞는 게 있을 때만 최대 1~2개 슬라이드에서 real_screenshot_asset_id로
지정하세요(AI 생성 이미지 대신 그 실제 화면이 쓰입니다). 없거나 안 맞으면 전부 null로 두세요."""


def _append_download_cta(caption: str, product: str, channel: str, products_by_name: dict[str, dict]) -> str:
    if channel == "instagram":
        # 인스타그램은 캡션 링크가 클릭되지 않아 프로필(bio) 링크를 안내한다
        return f"{caption}\n\n👉 앱 다운로드는 프로필 링크를 확인해주세요"

    row = products_by_name.get(_canonical_product(product))
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


async def marketing_worker_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    run_id = start_run(
        "MarketingWorker", {"ceo_directive": state["ceo_directive"]}, thread_id=thread_id
    )
    brief = state.get("worker_briefs", {}).get("marketing") or state["ceo_directive"]

    revision_note = state.get("revision_notes", {}).get("marketing")
    if revision_note:
        brief = f"{brief}\n\n[CEO 보완 요청 사유] {revision_note}"

    products_by_name = _fetch_products()

    related_docs = await rag_search(brief, limit=3)
    doc_context = "\n\n".join(f"[제품 특징 문서] {d['content']}" for d in related_docs)
    product_descriptions = "\n".join(
        f"[{name} 앱 설명] {row['description']}" for name, row in products_by_name.items() if row.get("description")
    )
    context = "\n\n".join(filter(None, [doc_context, product_descriptions])) or "(참고할 제품 문서 없음)"

    assets = (
        get_supabase().table("product_assets").select("id, product, description, storage_path").execute().data
    )
    assets_by_id = {a["id"]: a for a in assets}
    assets_context = (
        "[등록된 실제 앱 스크린샷 목록]\n"
        + "\n".join(f"- id={a['id']} product={a['product']}: {a['description']}" for a in assets)
        if assets
        else "(등록된 실제 스크린샷 없음)"
    )

    post = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"{brief}\n\n{context}\n\n{assets_context}"),
        ],
        MarketingPost,
        thread_id=thread_id,
        agent_name="MarketingWorker",
    )

    brand_color = _hex_to_rgb((products_by_name.get(_canonical_product(post.product)) or {}).get("brand_color"))
    total = len(post.slides)
    image_urls = []
    async with httpx.AsyncClient(timeout=30) as client:
        for i, slide in enumerate(post.slides):
            kwargs = {"page_label": f"{i + 1}/{total}"}
            if brand_color:
                kwargs["brand_color"] = brand_color

            asset = assets_by_id.get(slide.real_screenshot_asset_id or "")
            if asset:
                storage_path = asset["storage_path"]
                public_url = get_supabase().storage.from_("product-assets").get_public_url(storage_path)
                resp = await client.get(public_url)
                if resp.status_code == 200:
                    kwargs["illustration_bytes"] = resp.content

            card_bytes = await compose_marketing_card(
                slide.image_prompt,
                slide.headline,
                slide.subtext,
                post.product,
                thread_id=thread_id,
                agent_name="MarketingWorker",
                **kwargs,
            )
            image_urls.append(upload_marketing_image(card_bytes))

    caption = _append_download_cta(post.caption, post.product, post.channel, products_by_name)

    marketing_post = {
        "product": post.product,
        "channel": post.channel,
        "caption": caption,
        "slides": [s.model_dump() for s in post.slides],
        "image_urls": image_urls,
    }
    finish_run(run_id, marketing_post)
    return {
        "marketing_post": marketing_post,
        "messages": [
            {
                "role": "assistant",
                "content": f"[Marketing] {post.product}/{post.channel} 콘텐츠 생성 완료 ({total}장)",
            }
        ],
    }
