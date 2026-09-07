from app.db.agent_runs import finish_run, start_run
from app.db.supabase_client import get_supabase
from app.graphs.schemas import WBSPlan
from app.graphs.state import OSState
from app.tools.ai.llm import get_llm
from app.tools.ai.llm.base import Message

llm = get_llm()

SYSTEM_PROMPT = """당신은 CharisLab의 PM(CPO) 에이전트입니다. CEO의 지시(또는 신사업개발 에이전트의 사업기획서)를
실행 가능한 WBS(작업분할구조도)로 쪼개세요. 각 하위 작업에는 담당 부서(dept: CFO|CTO|CMO|CPO|CDO|CSO),
담당 에이전트, 현실적인 시작일/종료일(YYYY-MM-DD, 오늘 이후)을 지정하세요."""


async def pm_worker_node(state: OSState) -> dict:
    run_id = start_run("PMWorker", {"ceo_directive": state["ceo_directive"]})
    brief = state.get("worker_briefs", {}).get("pm") or state.get("biz_plan_brief") or state["ceo_directive"]

    wbs = await llm.complete_structured(
        [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=brief),
        ],
        WBSPlan,
    )

    supabase = get_supabase()
    parent = (
        supabase.table("tasks")
        .insert(
            {
                "title": wbs.project_title,
                "status": "todo",
                "dept": "CPO",
                "assignee_agent": "PMWorker",
            }
        )
        .execute()
    )
    parent_id = parent.data[0]["id"]

    created_tasks = []
    for item in wbs.tasks:
        task_row = (
            supabase.table("tasks")
            .insert(
                {
                    "title": item.title,
                    "status": "todo",
                    "dept": item.dept,
                    "assignee_agent": item.assignee_agent,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "wbs_parent_id": parent_id,
                }
            )
            .execute()
        )
        task = task_row.data[0]
        supabase.table("schedules").insert(
            {
                "project_id": parent_id,
                "task_id": task["id"],
                "calendar_start": item.start_date,
                "calendar_end": item.end_date,
            }
        ).execute()
        created_tasks.append(task)

    finish_run(run_id, {"project_id": parent_id, "task_count": len(created_tasks)})
    return {
        "wbs_plan": wbs.model_dump(),
        "schedule_progress": {"project_id": parent_id, "task_count": len(created_tasks)},
        "messages": [
            {
                "role": "assistant",
                "content": f"[PM] WBS 생성 완료: {wbs.project_title} ({len(created_tasks)}개 작업)",
            }
        ],
    }
