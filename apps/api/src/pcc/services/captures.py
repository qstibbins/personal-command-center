
from sqlalchemy import select
from sqlalchemy.orm import Session

from pcc.db.models import Capture
from pcc.schemas.capture import CaptureCreate


def create_capture(db: Session, data: CaptureCreate) -> Capture:
    capture = Capture(**data.model_dump())

    db.add(capture)
    db.commit()
    db.refresh(capture)

    return capture


def list_captures(db: Session, limit: int = 50) -> list[Capture]:
    statement = (
        select(Capture)
        .order_by(Capture.created_at.desc(), Capture.id.desc())
        .limit(limit)
    )

    return list(db.scalars(statement).all())
