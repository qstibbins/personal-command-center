
from collections.abc import Generator
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from pcc.db.session import SessionLocal
from pcc.schemas.capture import CaptureCreate, CaptureRead
from pcc.services.captures import create_capture, list_captures

router = APIRouter(
    prefix="/api/v1/captures",
    tags=["captures"],
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("", response_model=CaptureRead, status_code=201)
def post_capture(
    payload: CaptureCreate,
    db: Annotated[Session, Depends(get_db)],
):
    return create_capture(db, payload)


@router.get("", response_model=list[CaptureRead])
def get_captures(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=100),
):
    return list_captures(db, limit=limit)
