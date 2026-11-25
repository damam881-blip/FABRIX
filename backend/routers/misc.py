"""Small public endpoints: health-adjacent helpers and newsletter signup."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import NewsletterSubscriber
from ..schemas import Message, NewsletterIn
from fastapi import APIRouter, Depends, status

router = APIRouter(tags=["misc"])


@router.post("/newsletter", response_model=Message, status_code=status.HTTP_201_CREATED)
def subscribe(payload: NewsletterIn, db: Session = Depends(get_db)) -> Message:
    email = payload.email.lower().strip()
    existing = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == email))
    if existing:
        return Message(message="You are already subscribed")
    db.add(NewsletterSubscriber(email=email))
    db.commit()
    return Message(message="Thanks for joining! This demo does not send email.")
