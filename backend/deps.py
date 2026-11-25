"""Shared FastAPI dependencies for authentication and authorization."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .config import API_PREFIX
from .db import get_db
from .models import User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_PREFIX}/auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (ValueError, TypeError, KeyError):
        raise credentials_error from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
) -> User | None:
    """Return the current user when a valid token is present, else None."""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user = db.get(User, int(payload["sub"]))
    except (ValueError, TypeError, KeyError):
        return None
    return user if user and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*allowed: str, allow_seller: bool = False):
    """Build a dependency that allows only the given roles.

    ``allow_seller`` also accepts an approved store owner, matching the
    requirement that one FABRIX identity can both shop and sell.
    """

    def checker(user: CurrentUser) -> User:
        is_admin = user.role == "admin"
        is_active_seller = allow_seller and has_active_store(user)
        is_allowed = is_admin or user.role in allowed
        if allow_seller and "artisan" in allowed:
            is_allowed = is_admin or is_active_seller
        elif allow_seller:
            is_allowed = is_allowed or is_active_seller
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return checker


def has_active_store(user: User) -> bool:
    """Return whether the user's authoritative store permits selling."""
    return bool(
        user.store
        and user.store.state == "Approved"
        and user.can_sell
        and user.is_active
    )


require_customer = require_roles("customer", "artisan", "admin")
require_seller = require_roles("artisan", "admin", allow_seller=True)
require_artisan = require_seller
require_admin = require_roles("admin")
