from fastapi import APIRouter, Depends, HTTPException
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from pydantic import BaseModel

from app.auth.session import create_session_token, require_ceo
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    credential: str  # Google Identity Services가 프론트에서 발급하는 ID token


class GoogleLoginResponse(BaseModel):
    email: str
    name: str
    picture: str | None = None
    token: str


class MeResponse(BaseModel):
    email: str


@router.post("/google", response_model=GoogleLoginResponse)
def google_login(payload: GoogleLoginRequest) -> GoogleLoginResponse:
    try:
        info = id_token.verify_oauth2_token(
            payload.credential,
            google_requests.Request(),
            settings.google_oauth_client_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid google token") from exc

    email = info.get("email")
    if not email or email not in settings.allowed_email_list:
        raise HTTPException(status_code=403, detail="email not whitelisted")

    token = create_session_token(email)
    return GoogleLoginResponse(email=email, name=info.get("name", ""), picture=info.get("picture"), token=token)


@router.get("/me", response_model=MeResponse)
def me(email: str = Depends(require_ceo)) -> MeResponse:
    return MeResponse(email=email)
