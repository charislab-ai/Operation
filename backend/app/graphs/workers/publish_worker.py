from datetime import date

from langchain_core.runnables import RunnableConfig

from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.state import OSState
from app.tools.social import get_social_poster
from app.tools.telegram_bot import notify_ceo
from app.tools.social.base import PostContent


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

    finish_run(run_id, {"post_id": result.post_id, "permalink": result.permalink})

    # 게시가 끝나면 실제 게시물 링크를 바로 보내준다 - 예전엔 어디에 올라갔는지 확인할 방법이 없었다.
    link_text = result.permalink or f"(post_id: {result.post_id})"
    try:
        await notify_ceo(f"🚀 {post['product']} · {post['channel']} 게시 완료\n{link_text}")
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
