from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str
    dept: str
    assignee_agent: str
    status: str = "todo"
    start_date: date | None = None
    end_date: date | None = None
    wbs_parent_id: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    dept: str | None = None
    assignee_agent: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    progress_pct: int | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    status: str
    dept: str
    assignee_agent: str
    start_date: date | None = None
    end_date: date | None = None
    wbs_parent_id: str | None = None
    progress_pct: int = 0


@router.get("", response_model=list[TaskOut])
def list_tasks(
    dept: str | None = None, status: str | None = None, parent_id: str | None = None
) -> list[dict]:
    query = get_supabase().table("tasks").select("*")
    if dept:
        query = query.eq("dept", dept)
    if status:
        query = query.eq("status", status)
    if parent_id:
        query = query.eq("wbs_parent_id", parent_id)
    return query.execute().data


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str) -> dict:
    result = get_supabase().table("tasks").select("*").eq("id", task_id).single().execute()
    return result.data


@router.post("", response_model=TaskOut)
def create_task(payload: TaskCreate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    result = get_supabase().table("tasks").insert(data).execute()
    return result.data[0]


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    result = get_supabase().table("tasks").update(data).eq("id", task_id).execute()
    return result.data[0]


@router.delete("/{task_id}")
def delete_task(task_id: str) -> dict:
    get_supabase().table("tasks").delete().eq("id", task_id).execute()
    return {"ok": True}
