from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.tasks import TaskOut
from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/schedules", tags=["schedules"])


class ScheduleCreate(BaseModel):
    project_id: str
    task_id: str
    calendar_start: datetime | None = None
    calendar_end: datetime | None = None


class ScheduleOut(BaseModel):
    id: str
    project_id: str
    task_id: str
    calendar_start: datetime | None = None
    calendar_end: datetime | None = None
    task: TaskOut | None = None


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    start: datetime | None = None, end: datetime | None = None, with_task: bool = False
) -> list[dict]:
    select_clause = "*, task:tasks(*)" if with_task else "*"
    query = get_supabase().table("schedules").select(select_clause)
    if start:
        query = query.gte("calendar_start", start.isoformat())
    if end:
        query = query.lte("calendar_end", end.isoformat())
    return query.execute().data


@router.post("", response_model=ScheduleOut)
def create_schedule(payload: ScheduleCreate) -> dict:
    data = payload.model_dump(mode="json", exclude_none=True)
    result = get_supabase().table("schedules").insert(data).execute()
    return result.data[0]
