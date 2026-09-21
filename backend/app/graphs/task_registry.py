"""업무 지시(thread_id)별로 떠 있는 백그라운드 그래프 실행 asyncio.Task를 추적한다.

Why: "정지"/"강제 종료" 기능이 실제로 진행 중인 처리를 멈추려면 그 처리를 담당하는 태스크를
취소할 수 있어야 한다. Railway 배포가 uvicorn 단일 프로세스라(Dockerfile에 --workers 옵션
없음 확인) 인메모리 dict로 충분하다 - 여러 워커 프로세스로 확장하면 이 방식은 안 통하니 그때는
Redis 등 프로세스 간 공유 저장소로 옮겨야 한다.
"""

import asyncio

_tasks: dict[str, asyncio.Task] = {}


def register(thread_id: str, task: asyncio.Task) -> None:
    _tasks[thread_id] = task
    task.add_done_callback(lambda t, tid=thread_id: _tasks.pop(tid, None) if _tasks.get(tid) is t else None)


def cancel(thread_id: str) -> bool:
    """등록된 태스크가 있으면 취소를 요청한다. 취소를 "시도"했는지만 알려줄 뿐, 그래프 내부
    LLM/이미지 생성 호출 도중이면 다음 await 지점에서 CancelledError가 발생해 멈춘다."""
    task = _tasks.get(thread_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def is_running(thread_id: str) -> bool:
    task = _tasks.get(thread_id)
    return task is not None and not task.done()
