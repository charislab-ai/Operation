from app.db.agent_runs import finish_run, start_run
from app.graphs.schemas import MarketingPost
from app.graphs.state import OSState
from app.tools.ai.image.card_composer import compose_marketing_card
from app.tools.ai.image.storage import upload_marketing_image
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message
from app.workers.rag_worker import rag_search

llm = get_llm()

# 사용자에게 실제 앱스토어/플레이스토어 링크를 요청해둔 상태 - 받는 대로 채워넣을 것.
# LLM이 URL을 임의로 지어내면 안 되므로(실제로 존재하지 않는 링크를 게시할 위험) 캡션의
# 다운로드 링크는 LLM 생성물이 아니라 여기서 코드로 확정해 붙인다.
PRODUCT_STORE_LINKS: dict[str, str] = {}

SYSTEM_PROMPT = """당신은 CharisLab의 마케팅(CMO) 에이전트입니다. CEO의 지시와 (있다면) 제품 특징 문서를
참고해서 홍보할 제품(product), 게시할 채널(channel: instagram|facebook|tiktok|threads), 게시물
전체 캡션(caption), 카드뉴스 슬라이드 목록(slides, 3~5장)을 만드세요. 채널이 명시되지 않으면 지시
맥락상 가장 적합한 채널 하나를 고르세요. 제품 특징 문서가 있으면 막연한 감성 문구 대신 실제 기능이
드러나는 구체적인 문구를 우선하세요.

슬라이드 구성: 1번은 후킹 헤드라인, 중간 슬라이드들은 기능/베네핏을 하나씩, 마지막은 CTA로
구성하세요(예: "지금 다운로드하고 시작하세요"). 캡션에는 다운로드 링크를 직접 쓰지 마세요(별도로
붙습니다).

이미지 프롬프트 작성 규칙(슬라이드마다):
- 컬러풀하고 실사에 가까운 사진 스타일, 너무 매끈한 스톡사진 느낌보다 살짝 캐주얼한 스냅샷 느낌
- **등장인물은 반드시 한국인(Korean people)으로 명시**하세요 — "Korean family"/"Korean
  friends"/"Korean office coworkers" 등으로 구체적으로 적으세요
- SnapTale은 가족뿐 아니라 친구, 취미, 일상, 직장 등 다양한 주제별 앨범을 지원하는 제품입니다.
  지시 내용에 특정 장면이 없다면 매번 가족으로만 고정하지 말고, 지시 맥락에 맞춰 가족/친구 모임/
  취미 활동(등산·요리·운동 등)/일상 나들이/직장 동료들과의 업무 사진 등 다양한 장면 중 하나를
  선택해 폭넓은 사용 사례를 보여주세요
- 텍스트/로고는 이미지에 넣지 말라고 명시하세요(헤드라인/보조문구는 별도로 합성됩니다)"""


def _append_download_cta(caption: str, product: str, channel: str) -> str:
    if channel == "instagram":
        return f"{caption}\n\n👉 앱 다운로드는 프로필 링크를 확인해주세요"
    link = PRODUCT_STORE_LINKS.get(product)
    if link:
        return f"{caption}\n\n👉 지금 다운로드: {link}"
    return caption  # 링크 미확보 상태 - 확보되면 자동으로 위 분기를 타게 됨


async def marketing_worker_node(state: OSState) -> dict:
    run_id = start_run("MarketingWorker", {"ceo_directive": state["ceo_directive"]})
    brief = state.get("worker_briefs", {}).get("marketing") or state["ceo_directive"]

    related_docs = await rag_search(brief, limit=3)
    context = (
        "\n\n".join(f"[제품 특징 문서] {d['content']}" for d in related_docs)
        if related_docs
        else "(참고할 제품 문서 없음)"
    )

    post = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=f"{brief}\n\n{context}"),
        ],
        MarketingPost,
    )

    total = len(post.slides)
    image_urls = []
    for i, slide in enumerate(post.slides):
        card_bytes = await compose_marketing_card(
            slide.image_prompt, slide.headline, slide.subtext, post.product, page_label=f"{i + 1}/{total}"
        )
        image_urls.append(upload_marketing_image(card_bytes))

    caption = _append_download_cta(post.caption, post.product, post.channel)

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
