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
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be 72 UTF-8 bytes or fewer.")
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > 72:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


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
            "sessionVersion": user.get("sessionVersion", 0),
        },
    )


def create_refresh_token(user: dict) -> str:
    return create_token(
        subject=str(user["_id"]),
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        extra={"sessionVersion": user.get("sessionVersion", 0)},
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


def ensure_current_session(payload: dict, user: dict) -> None:
    if payload.get("sessionVersion", 0) != user.get("sessionVersion", 0):
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")


PASSWORD_RESET_REQUIRED_DETAIL = "password_reset_required"


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Resolve the signed-in user without applying the forced-reset gate.

    Only the routes that let a user out of that state may depend on this.
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    payload = decode_token(credentials.credentials, expected_type="access")
    if not ObjectId.is_valid(payload.get("sub", "")):
        raise HTTPException(status_code=401, detail="Invalid token subject.")
    db = get_database()
    user = await db.users.find_one({"_id": ObjectId(payload["sub"]), "status": "active"})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")
    ensure_current_session(payload, user)
    return user


async def get_current_user(user: dict = Depends(get_authenticated_user)) -> dict:
    if user.get("mustResetPassword"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_RESET_REQUIRED_DETAIL)
    return user


async def require_auth_in_production(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    """Restrict diagnostics even when a development server is exposed by a tunnel."""
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    user = await get_authenticated_user(credentials)
    await get_current_user(user)
    if user.get("globalRole") != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform admin access required.")
    return user


async def get_current_business_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("accountType") != "business_owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Business account required.")
    return current_user


async def get_current_customer_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("accountType") != "customer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Customer account required.")
    return current_user


async def get_current_cashier_user(current_user: dict = Depends(get_current_user)) -> dict:
    """A cashier account, already proven to belong to exactly one business.

    Every cashier route depends on this rather than on ``get_current_user`` so a cashier
    token can never be replayed against an owner, admin, or customer endpoint, and so the
    tenant a cashier may act on is taken from the account rather than from the request.
    """
    if current_user.get("accountType") != "cashier":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cashier account required.")
    if not current_user.get("tenantId"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This cashier is not linked to a business.")
    return current_user
