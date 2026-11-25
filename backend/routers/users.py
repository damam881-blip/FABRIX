"""Current-user profile, address, and notification endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import CurrentUser, DbSession
from ..models import Address, Notification, RecommendationEvent
from ..schemas import (
    AddressIn,
    AddressOut,
    Message,
    NotificationList,
    NotificationOut,
    UserOut,
    UserUpdate,
)
from ..services import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_profile(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_profile(payload: UserUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        if value is not None and isinstance(value, str):
            value = value.strip() or None
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.get("/me/addresses", response_model=list[AddressOut])
def list_addresses(user: CurrentUser, db: DbSession) -> list[AddressOut]:
    rows = db.scalars(
        select(Address).where(Address.user_id == user.id).order_by(Address.created_at.desc())
    ).all()
    return [AddressOut.model_validate(row) for row in rows]


@router.post("/me/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(payload: AddressIn, user: CurrentUser, db: DbSession) -> AddressOut:
    count = db.scalar(select(func.count(Address.id)).where(Address.user_id == user.id)) or 0
    if count >= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum of 5 addresses")
    data = payload.model_dump()
    if data["is_default"]:
        for row in db.scalars(select(Address).where(Address.user_id == user.id)).all():
            row.is_default = False
    row = Address(user_id=user.id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return AddressOut.model_validate(row)


@router.patch("/me/addresses/{address_id}", response_model=AddressOut)
def update_address(address_id: int, payload: AddressIn, user: CurrentUser, db: DbSession) -> AddressOut:
    row = db.scalar(select(Address).where(Address.id == address_id, Address.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    data = payload.model_dump()
    if data["is_default"]:
        for other in db.scalars(select(Address).where(Address.user_id == user.id)).all():
            other.is_default = False
    for field, value in data.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return AddressOut.model_validate(row)


@router.delete("/me/addresses/{address_id}", response_model=Message)
def delete_address(address_id: int, user: CurrentUser, db: DbSession) -> Message:
    row = db.scalar(select(Address).where(Address.id == address_id, Address.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found")
    db.delete(row)
    db.commit()
    return Message(message="Address removed")


@router.get("/me/notifications", response_model=NotificationList)
def list_notifications(user: CurrentUser, db: DbSession) -> NotificationList:
    rows = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        ).all()
    )
    return NotificationList(
        items=[NotificationOut.model_validate(row) for row in rows],
        total=len(rows),
        unread=sum(1 for row in rows if not row.is_read),
    )


@router.patch("/me/notifications/{notification_id}", response_model=NotificationOut)
def mark_notification_read(notification_id: int, user: CurrentUser, db: DbSession) -> NotificationOut:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return NotificationOut.model_validate(row)


@router.post("/me/notifications/read-all", response_model=Message)
def mark_all_notifications_read(user: CurrentUser, db: DbSession) -> Message:
    for row in db.scalars(select(Notification).where(Notification.user_id == user.id)).all():
        row.is_read = True
    db.commit()
    return Message(message="All notifications marked as read")


@router.delete("/me/recommendation-data", response_model=Message)
def delete_recommendation_data(user: CurrentUser, db: DbSession) -> Message:
    deleted = db.query(RecommendationEvent).filter(
        RecommendationEvent.user_id == user.id
    ).delete(synchronize_session=False)
    user.consent = False
    user.personalization = False
    audit(
        db,
        "recommendation.privacy_deleted",
        actor_id=user.id,
        target_type="user",
        target_id=user.id,
        metadata={"deleted_events": deleted},
    )
    db.commit()
    return Message(message=f"Deleted {deleted} recommendation events and disabled personalization")
