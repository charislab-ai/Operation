from datetime import date

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.state import OSState
from app.tools.social import get_social_poster
from app.tools.telegram_bot import notify_ceo
from app.tools.social.base import PostContent


async def _post_download_comment(poster, post_id: str, product: str) -> str | None:
    """게시물 첫 댓글에 앱 다운로드 링크를 단다. 실패하면 None(게시는 이미 끝났으므로 막지 않음)."""
    if not hasattr(poster, "post_comment"):
        return None  # mock 어댑터 등 - 댓글 개념이 없는 경로
    from app.graphs.workers._marketing_shared import canonical_product, fetch_products

    row = fetch_products().get(canonical_product(product)) or {}
    links = []
    if row.get("ios_url"):
        links.append(f"iOS: {row['ios_url']}")
    if row.get("android_url"):
        links.append(f"Android: {row['android_url']}")
    if not links:
        return None  # 스토어 링크가 등록돼 있지 않으면 댓글을 달 이유가 없다
    message = f"📲 {product} 다운로드 (무료)\n" + "\n".join(links)
    return await poster.post_comment(post_id, message)


async def publish_worker_node(state: OSState, config: RunnableConfig) -> dict:
    thread_id = config["configurable"]["thread_id"]
    post = state["marketing_post"]
    run_id = start_run(
        "PublishWorker",
        {"product": post["product"], "channel": post["channel"]},
        thread_id=thread_id,
    )
    poster = get_social_poster(post["channel"], post["product"])
    result = await poster.post(PostContent(caption=post["caption"], image_urls=post["image_urls"]))

    # 조회수/클릭은 실제 Insights API를 붙이기 전까지 기록하지 않는다 - 예전엔 난수로 지어낸
    # 숫자를 저장해서 그걸로 성과를 판단할 위험이 있었다(CEO 지적으로 제거).
    get_supabase().table("marketing_metrics").insert(
        {
            "product": post["product"],
            "channel": post["channel"],
            "metric_date": date.today().isoformat(),
            "post_id": result.post_id,
            "permalink": result.permalink,
        }
    ).execute()

    # 인스타그램은 캡션 안 URL이 클릭되지 않아, 다운로드 링크를 첫 댓글로 단다(실무 표준).
    # 토큰에 instagram_manage_comments 권한이 없으면 실패하지만, 그때는 조용히 넘기고 CEO에게
    # 알림 문구로 알려 직접 달 수 있게 한다(게시 자체는 이미 성공).
    comment_link = await _post_download_comment(poster, result.post_id, post["product"])

    finish_run(
        run_id,
        {"post_id": result.post_id, "permalink": result.permalink, "link_comment": comment_link},
    )

    # 게시가 끝나면 실제 게시물 링크를 바로 보내준다 - 예전엔 어디에 올라갔는지 확인할 방법이 없었다.
    link_text = result.permalink or f"(post_id: {result.post_id})"
    comment_note = (
        "\n💬 다운로드 링크를 첫 댓글로 등록했습니다"
        if comment_link
        else "\n⚠️ 다운로드 링크 댓글은 권한이 없어 등록하지 못했습니다 - 직접 달아주세요"
    )
    try:
        await notify_ceo(f"🚀 {post['product']} · {post['channel']} 게시 완료\n{link_text}{comment_note}")
    except Exception:
        pass

    return {
        "messages": [
            {
                "role": "assistant",
                "content": f"[Publish] {post['channel']}에 게시 완료 ({link_text})",
            }
        ],
    }
