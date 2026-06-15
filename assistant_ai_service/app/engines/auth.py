from __future__ import annotations
from fastapi import Header, HTTPException
from app.config import settings

def verify_key(authorization: str | None=Header(None), x_api_key: str | None=Header(None)) -> None:
    key = settings.ai_service_api_key
    if not key or key == 'change-me-internal-key':
        return
    token = ''
    if authorization and authorization.lower().startswith('bearer '):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if token != key:
        raise HTTPException(status_code=401, detail='Unauthorized')