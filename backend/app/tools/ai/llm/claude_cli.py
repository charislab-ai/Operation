import asyncio
import json

from app.db.ai_usage import log_ai_usage
from app.tools.ai.llm.base import Message, SchemaT

# Goal형 병렬 실행으로 여러 Worker가 동시에 LLM을 호출할 수 있게 되면서 실제로 겪은 문제:
# `claude` CLI 프로세스 2개를 진짜로 동시에 띄우면 간헐적으로 stdout에 다른 프로세스의 응답이
# 섞여 들어와("Extra data" JSON 파싱 오류) 실측으로 재현됨. Worker들의 그래프 실행 자체는
# 병렬로 두되, CLI 서브프로세스 호출만 이 세마포어로 한 번에 하나씩 순서대로 실행한다.
_CLI_LOCK = asyncio.Semaphore(1)


class ClaudeCLIUnavailable(Exception):
    """claude CLI 실행 실패 또는 사용량 한도 초과 — 상위(get_llm)에서 API로 폴백해야 함을 알린다."""


def _split_system_and_prompt(messages: list[Message]) -> tuple[str | None, str]:
    system_parts = [m.content for m in messages if m.role == "system"]
    user_parts = [m.content for m in messages if m.role != "system"]
    return ("\n\n".join(system_parts) or None, "\n\n".join(user_parts))


async def _run_cli(system: str | None, prompt: str, json_schema: dict | None = None) -> dict:
    args = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--tools",
        "",  # 순수 텍스트/구조화 출력 용도라 파일/Bash 등 도구 접근은 비활성화
        "--no-session-persistence",
    ]
    if system:
        args += ["--append-system-prompt", system]
    if json_schema:
        args += ["--json-schema", json.dumps(json_schema)]

    try:
        async with _CLI_LOCK:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90.0)
    except (FileNotFoundError, TimeoutError) as exc:
        raise ClaudeCLIUnavailable(f"claude CLI 실행 불가: {exc}") from exc

    if proc.returncode != 0:
        raise ClaudeCLIUnavailable(f"claude CLI exit={proc.returncode}: {stderr.decode()[:500]}")

    try:
        response = json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        raise ClaudeCLIUnavailable(f"claude CLI 응답 파싱 실패: {exc}") from exc

    # is_error/api_error_status는 사용량 한도 초과를 포함한 모든 실패를 포괄한다 —
    # 원인을 세분화하지 않고 API로 폴백하는 것이 이 시스템의 방침이다.
    if response.get("is_error") or response.get("api_error_status") is not None:
        raise ClaudeCLIUnavailable(f"claude CLI 오류 응답: {response.get('subtype')}")

    return response


def _log_cli_usage(response: dict, thread_id: str | None, agent_name: str | None) -> None:
    usage = response.get("usage") or {}
    total = None
    if usage.get("input_tokens") is not None or usage.get("output_tokens") is not None:
        total = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
    log_ai_usage(
        thread_id=thread_id,
        agent_name=agent_name,
        provider="claude_cli",
        kind="llm",
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=total,
        cost_usd=response.get("total_cost_usd"),  # CLI가 주는 실제 $ 금액 - 유일하게 신뢰 가능한 비용 소스
    )


def _require_text_only(messages: list[Message]) -> None:
    """CLI 경로는 표준입력으로 텍스트만 넘기므로 이미지가 붙은 요청(브랜드 QA 검수)은 처리할 수
    없다 - 조용히 이미지를 버리고 "보지 않은 채" 판정하면 안 되므로, 폴백(API)으로 넘긴다."""
    if any(m.images for m in messages):
        raise ClaudeCLIUnavailable("claude CLI는 이미지 입력을 지원하지 않음 - API로 폴백")


class ClaudeCLIProvider:
    """Claude Code CLI(구독 플랜)를 통해 추론한다. 실패/한도초과 시 ClaudeCLIUnavailable을 던진다."""

    async def complete(
        self,
        messages: list[Message],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        _require_text_only(messages)
        system, prompt = _split_system_and_prompt(messages)
        response = await _run_cli(system, prompt)
        _log_cli_usage(response, thread_id, agent_name)
        return response.get("result", "")

    async def complete_structured(
        self,
        messages: list[Message],
        schema: type[SchemaT],
        *,
        thread_id: str | None = None,
        agent_name: str | None = None,
    ) -> SchemaT:
        _require_text_only(messages)
        system, prompt = _split_system_and_prompt(messages)
        response = await _run_cli(system, prompt, json_schema=schema.model_json_schema())
        _log_cli_usage(response, thread_id, agent_name)
        structured = response.get("structured_output")
        if structured is None:
            raise ClaudeCLIUnavailable("claude CLI가 structured_output을 반환하지 않음")
        return schema.model_validate(structured)
