from fastapi import APIRouter, Depends, Query
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/events")
def get_events(
    source: str | None = Query(None),
    start_after: str | None = Query(None),
    end_before: str | None = Query(None),
    db: PlannerDB = Depends(get_db),
):
    return db.get_events(source=source, start_after=start_after, end_before=end_before)
