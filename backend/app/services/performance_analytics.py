"""게시 성과를 분석해 "다음에 뭘 해야 하는가"의 근거를 만든다.

Why 코드로 계산하는가: 퍼포먼스 마케터에게 원본 데이터를 통째로 던지고 "분석해줘"라고 하면
LLM이 숫자를 잘못 더하거나 없는 추세를 지어낸다. 집계·정렬·비교처럼 틀리면 안 되는 계산은
코드가 하고, LLM은 그 결과를 보고 **판단**만 하게 한다(무엇을 만들지 정하는 게 LLM의 일).

인스타는 공유 > 저장 > 댓글 > 좋아요 순으로 강한 신호로 보므로, 단순 조회수가 아니라
"퍼짐 점수"로 순위를 매긴다.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from app.db.supabase_client import get_supabase

# 인스타 알고리즘이 보는 신호의 상대적 무게(공식 수치가 아니라 업계 통설 기준의 가중치 -
# 절대값이 아니라 "무엇이 더 잘 퍼졌는가"를 비교하는 용도로만 쓴다)
_WEIGHTS = {"shares": 5.0, "saved": 3.0, "comments": 2.0, "likes": 1.0}


# 도달 분모에 더하는 완충값. 실측: 도달 1에 좋아요 1뿐인 게시물이 퍼짐 100점으로 1위가 됐다
# (2026-09-13 터치러쉬). 표본이 극히 작은 게시물이 순위를 지배하지 않도록 분모를 띄워,
# 도달이 충분히 쌓인 게시물만 높은 점수에 도달할 수 있게 한다.
_REACH_PRIOR = 20


def _spread_score(post: dict) -> float:
    """퍼짐 점수 - 도달 대비 반응이 얼마나 강했는지. 도달 표본이 작으면 점수를 보수적으로 깎는다."""
    reach = max(0, post.get("reach") or 0)
    raw = sum(_WEIGHTS[k] * (post.get(k) or 0) for k in _WEIGHTS)
    return round(raw / (reach + _REACH_PRIOR) * 100, 1)


def _fmt(post: dict) -> str:
    return "릴스" if (post.get("media_type") or "") in ("VIDEO", "REELS") else "피드"


def analyze(days: int = 90) -> dict:
    """게시 성과를 집계해 퍼포먼스 마케터가 판단할 재료를 만든다."""
    supabase = get_supabase()
    since = (date.today() - timedelta(days=days)).isoformat()
    posts = (
        supabase.table("marketing_metrics")
        .select("product, channel, media_type, metric_date, permalink, views, reach, saved, shares, likes, comments")
        .gte("metric_date", since)
        .order("metric_date", desc=True)
        .execute()
        .data
    )
    measured = [p for p in posts if p.get("reach") is not None]

    by_product: dict[str, dict] = defaultdict(lambda: {"posts": 0, "reach": 0, "saved": 0, "shares": 0, "scores": []})
    by_format: dict[str, dict] = defaultdict(lambda: {"posts": 0, "reach": 0, "scores": []})
    last_posted: dict[str, str] = {}

    for p in posts:
        product = p.get("product") or "?"
        if p["metric_date"] > last_posted.get(product, ""):
            last_posted[product] = p["metric_date"]
        if p.get("reach") is None:
            continue
        score = _spread_score(p)
        bp = by_product[product]
        bp["posts"] += 1
        bp["reach"] += p.get("reach") or 0
        bp["saved"] += p.get("saved") or 0
        bp["shares"] += p.get("shares") or 0
        bp["scores"].append(score)
        bf = by_format[_fmt(p)]
        bf["posts"] += 1
        bf["reach"] += p.get("reach") or 0
        bf["scores"].append(score)

    def _summarize(bucket: dict) -> dict:
        n = max(1, bucket["posts"])
        return {
            **{k: v for k, v in bucket.items() if k != "scores"},
            "avg_reach": round(bucket["reach"] / n),
            "avg_spread": round(sum(bucket["scores"]) / n, 1) if bucket["scores"] else 0,
        }

    today = date.today()
    gaps = {}
    for product, last in last_posted.items():
        try:
            gaps[product] = (today - datetime.fromisoformat(last).date()).days
        except ValueError:
            continue

    ranked = sorted(measured, key=_spread_score, reverse=True)
    account = (
        supabase.table("account_snapshots")
        .select("snapshot_date, followers, reach, profile_views")
        .order("snapshot_date", desc=True)
        .limit(14)
        .execute()
        .data
    )

    # 한 번도 안 올린 제품은 "간격 무한대"로 본다 - 노출 기회를 못 받은 제품을 찾기 위함
    all_products = [r["name"] for r in supabase.table("products").select("name").execute().data]
    never_posted = [p for p in all_products if p not in last_posted]

    return {
        "measured_posts": len(measured),
        "total_posts": len(posts),
        "by_product": {k: _summarize(v) for k, v in by_product.items()},
        "by_format": {k: _summarize(v) for k, v in by_format.items()},
        "days_since_last_post": gaps,
        "never_posted": never_posted,
        "best": [
            {
                "product": p.get("product"),
                "format": _fmt(p),
                "date": p.get("metric_date"),
                "reach": p.get("reach"),
                "saved": p.get("saved"),
                "shares": p.get("shares"),
                "spread": _spread_score(p),
                "permalink": p.get("permalink"),
            }
            for p in ranked[:3]
        ],
        "worst": [
            {
                "product": p.get("product"),
                "format": _fmt(p),
                "date": p.get("metric_date"),
                "reach": p.get("reach"),
                "spread": _spread_score(p),
            }
            for p in ranked[-2:]
        ]
        if len(ranked) > 3
        else [],
        "account_trend": account[:7],
        "followers": account[0]["followers"] if account else None,
    }


def as_brief(analysis: dict) -> str:
    """분석 결과를 퍼포먼스 마케터가 읽을 브리핑 텍스트로 만든다."""
    if analysis["measured_posts"] == 0:
        return (
            "[성과 데이터]\n아직 측정된 게시물이 없습니다. 성과를 근거로 고를 수 없으니, "
            "게시 간격이 가장 긴 제품을 고르고 그 사실을 rationale에 솔직히 적으세요."
        )
    lines = [
        f"[성과 데이터] 측정된 게시물 {analysis['measured_posts']}건 · 팔로워 {analysis['followers']}명",
        "",
        "제품별(퍼짐 점수 = 도달 대비 공유·저장·댓글 가중 반응):",
    ]
    for product, v in sorted(analysis["by_product"].items(), key=lambda x: -x[1]["avg_spread"]):
        lines.append(
            f"  - {product}: {v['posts']}건 · 평균 도달 {v['avg_reach']} · 퍼짐 {v['avg_spread']} "
            f"· 저장 {v['saved']} · 공유 {v['shares']}"
        )
    lines.append("")
    lines.append("형식별:")
    for fmt, v in sorted(analysis["by_format"].items(), key=lambda x: -x[1]["avg_reach"]):
        lines.append(f"  - {fmt}: {v['posts']}건 · 평균 도달 {v['avg_reach']} · 퍼짐 {v['avg_spread']}")
    lines.append("")
    lines.append("마지막 게시 이후 경과일:")
    for product, gap in sorted(analysis["days_since_last_post"].items(), key=lambda x: -x[1]):
        lines.append(f"  - {product}: {gap}일")
    for product in analysis["never_posted"]:
        lines.append(f"  - {product}: 한 번도 게시 안 함")
    if analysis["best"]:
        lines.append("")
        lines.append("가장 잘 퍼진 게시물:")
        for b in analysis["best"]:
            lines.append(
                f"  - {b['date']} {b['product']} {b['format']}: 도달 {b['reach']} "
                f"· 저장 {b['saved']} · 공유 {b['shares']} · 퍼짐 {b['spread']}"
            )
    return "\n".join(lines)
