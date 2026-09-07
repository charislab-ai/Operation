from typing import Protocol


class GoogleCalendarSync(Protocol):
    """PMWorker가 CEO 개인/외부 캘린더와 Calendar View(schedules)를 양방향 동기화할 때 쓸 인터페이스.

    ARCHITECTURE.md §6 참고. Phase 1에서는 인터페이스만 정의하고
    settings.google_calendar_mcp_enabled=False로 비활성 상태를 유지한다 (Phase 1은 §5 참고, 실제 동기화는 이후 Phase).
    """

    async def push_schedule(self, task_id: str, start: str, end: str) -> None: ...

    async def pull_events(self) -> list[dict]: ...
