from app.db.supabase_client import get_supabase


def log_ai_usage(
    *,
    thread_id: str | None,
    agent_name: str | None,
    provider: str,  # "claude_cli"|"claude_api"|"dalle"|"mock"
    kind: str,  # "llm"|"image"
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    image_count: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """AI 사용량 기록 - best-effort. 로깅 실패가 실제 지시 처리(그래프 실행)를
    막으면 안 되므로 예외를 삼킨다."""
    try:
        get_supabase().table("ai_usage_log").insert(
            {
                "thread_id": thread_id,
                "agent_name": agent_name,
                "provider": provider,
                "kind": kind,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "image_count": image_count,
                "cost_usd": cost_usd,
            }
        ).execute()
    except Exception:
        pass
