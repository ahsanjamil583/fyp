from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.db.mongodb import get_database

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user: dict) -> str:
    return create_token(
        subject=str(user["_id"]),
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        extra={
            "accountType": user.get("accountType"),
            "globalRole": user.get("globalRole"),
        },
    )


def create_refresh_token(user: dict) -> str:
    return create_token(
        subject=str(user["_id"]),
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        ) from exc

    if payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
        )
    return payload


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    payload = decode_token(credentials.credentials, expected_type="access")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(payload["sub"]), "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    return user


async def get_current_business_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("accountType") != "business_owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business account required.")
    return current_user


async def get_current_customer_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("accountType") != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer account required.")
    return current_user
