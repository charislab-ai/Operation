import json
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic

from app.config import settings
from app.db.ai_usage import log_ai_usage
from app.tools.ai.llm.base import Message, SchemaT


@lru_cache
def _model() -> ChatAnthropic:
    # temperature를 명시하면 일부 최신 모델(예: claude-sonnet-5)이 "temperature is deprecated
    # for this model" 400 에러를 반환해 폴백 경로 자체가 죽는 걸 실측으로 확인 - 기본값 사용
    return ChatAnthropic(
        model=settings.anthropic_model,
        anthropic_api_key=settings.anthropic_api_key,
        max_tokens=4096,
    )


def _to_lc_messages(messages: list[Message]) -> list[tuple[str, str]]:
    return [(m.role, m.content) for m in messages]


def _recover_from_malformed_tool_call(raw: Any, schema: type[SchemaT]) -> dict | None:
    """with_structured_output가 parsed=None을 반환할 때가 있음(실측 확인 - 인스타툰 VisualPlan
    구조화 출력에서 재현됨). Claude가 가끔 tool 호출 인자 전체를 JSON 문자열 하나로 감싸서 보내서
    (예: args={"slides": "{\\"slides\\": [...]}"} 처럼 실제 배열이 문자열 안에 또 들어있음)
    langchain의 1차 파싱이 실패하는 케이스 - raw tool_calls를 직접 열어서 문자열로 감싸진 JSON을
    풀어보고 재검증한다."""
    tool_calls = getattr(raw, "tool_calls", None) or []
    for call in tool_calls:
        args = call.get("args") if isinstance(call, dict) else None
        if not isinstance(args, dict):
            continue
        for value in args.values():
            if not isinstance(value, str):
                continue
            try:
                candidate = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(candidate, dict):
                try:
                    schema.model_validate(candidate)
                except Exception:
                    continue
                return candidate
        try:
            schema.model_validate(args)
        except Exception:
            continue
        return args
    return None


class ClaudeLLMProvider:
    """LLMProvider 구현체 — Claude(Anthropic)를 기본 추론 엔진으로 사용한다."""

    async def complete(
        self,
        messages: list[Message],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        result = await _model().ainvoke(_to_lc_messages(messages))
        usage = getattr(result, "usage_metadata", None) or {}
        log_ai_usage(
            thread_id=thread_id,
            agent_name=agent_name,
            provider="claude_api",
            kind="llm",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        return str(result.content)

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> SchemaT:
        # include_raw=True로 받아야 raw AIMessage의 usage_metadata에 접근 가능
        # (파싱된 결과만 받으면 토큰 사용량이 버려짐)
        structured_model = _model().with_structured_output(schema, include_raw=True)
        result = await structured_model.ainvoke(_to_lc_messages(messages))
        raw = result.get("raw")
        usage = (getattr(raw, "usage_metadata", None) or {}) if raw else {}
        log_ai_usage(
            thread_id=thread_id,
            agent_name=agent_name,
            provider="claude_api",
            kind="llm",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        parsed = result.get("parsed")
        if parsed is None:
            parsed = _recover_from_malformed_tool_call(raw, schema)
        return schema.model_validate(parsed)
