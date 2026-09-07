from fastapi import APIRouter
from pydantic import BaseModel

from app.db.supabase_client import get_supabase

router = APIRouter(prefix="/office", tags=["office"])


class DeskCreate(BaseModel):
    room: str
    grid_x: int
    grid_y: int
    dept: str | None = None
    label: str | None = None


class DeskOut(BaseModel):
    id: str
    room: str
    grid_x: int
    grid_y: int
    dept: str | None = None
    label: str | None = None


@router.get("/desks", response_model=list[DeskOut])
def list_desks() -> list[dict]:
    return get_supabase().table("office_desks").select("*").execute().data


@router.post("/desks", response_model=DeskOut)
def create_desk(payload: DeskCreate) -> dict:
    data = payload.model_dump(exclude_none=True)
    result = get_supabase().table("office_desks").insert(data).execute()
    return result.data[0]


@router.delete("/desks/{desk_id}")
def delete_desk(desk_id: str) -> dict:
    get_supabase().table("office_desks").delete().eq("id", desk_id).execute()
    return {"ok": True}
