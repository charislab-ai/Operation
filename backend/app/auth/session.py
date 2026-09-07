from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, Query

from app.config import settings

ALGORITHM = "HS256"


def create_session_token(email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": email, "iat": now, "exp": now + timedelta(hours=settings.session_ttl_hours)}
    return jwt.encode(payload, settings.session_secret, algorithm=ALGORITHM)


def _decode(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired session") from exc

    email = payload.get("sub")
    if not email or email not in settings.allowed_email_list:
        raise HTTPException(status_code=403, detail="email not whitelisted")
    return email


def require_ceo(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
) -> str:
    """REST 요청은 Authorization 헤더, WebSocket은 쿼리파라미터로 세션 토큰을 받는다
    (브라우저 WebSocket API는 커스텀 헤더를 지원하지 않음)."""
    raw = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:]
    elif token:
        raw = token

    if not raw:
        raise HTTPException(status_code=401, detail="missing session token")
    return _decode(raw)
