"""Registration, login, and current-user identity endpoints."""
from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser
from ..models import SellerApplication, Store, User
from ..schemas import LoginRequest, Message, RegisterRequest, Token, UserOut
from ..security import create_access_token, hash_password, verify_password
from ..utils import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
_LOGIN_WINDOW_SECONDS = 60.0
_LOGIN_FAILURE_LIMIT = 5
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_lock = Lock()


def _login_key(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    return f"{client}:{email}"


def _is_login_limited(key: str, now: float) -> bool:
    with _login_lock:
        attempts = _login_failures[key]
        while attempts and now - attempts[0] >= _LOGIN_WINDOW_SECONDS:
            attempts.popleft()
        return len(attempts) >= _LOGIN_FAILURE_LIMIT


def _record_login_failure(key: str, now: float) -> None:
    with _login_lock:
        _login_failures[key].append(now)


def _clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)


def _token_for(user: User) -> Token:
    return Token(
        access_token=create_access_token(user.id, user.role),
        token_type="bearer",
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower().strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    # Administrative accounts are provisioned out-of-band. Public
    # registration can create a customer identity or an artisan draft, never
    # an administrator and never an already-approved store.
    is_artisan = payload.role == "artisan"
    now = utcnow()
    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=payload.role,
        can_shop=True,
        can_sell=False,
        studio_name=payload.studio_name,
        studio_story=payload.studio_story,
        consent=payload.consent,
        personalization=payload.personalization,
    )
    db.add(user)
    db.flush()

    if is_artisan:
        studio_name = (payload.studio_name or user.full_name).strip()
        story = (payload.studio_story or "").strip() or "FABRIX maker studio."
        db.add(
            Store(
                user_id=user.id,
                name=studio_name,
                story=story,
                craft="Textiles",
                state="Draft",
                notes="Complete the studio profile and submit it for admin review.",
                submitted_at=now,
            )
        )
        db.add(
            SellerApplication(
                user_id=user.id,
                studio_name=studio_name,
                craft="Textiles",
                story=story,
                status="draft",
            )
        )

    db.commit()
    db.refresh(user)
    return _token_for(user)


@router.post("/login", response_model=Token)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    email = payload.email.lower().strip()
    key = _login_key(request, email)
    now = monotonic()
    if _is_login_limited(key, now):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts; try again later",
            headers={"Retry-After": str(int(_LOGIN_WINDOW_SECONDS))},
        )
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        _record_login_failure(key, now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        _record_login_failure(key, now)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is inactive")

    if payload.role and user.role != payload.role and user.role != "admin":
        _record_login_failure(key, now)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This account uses the {user.role} experience",
        )
    _clear_login_failures(key)
    return _token_for(user)


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/logout", response_model=Message)
def logout(_: CurrentUser) -> Message:
    # JWTs are stateless; the browser client discards the token. This endpoint
    # exists so clients can use a consistent API shape.
    return Message(message="Signed out. Discard your access token.")
