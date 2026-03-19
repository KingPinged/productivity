from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/schedule/{date}")
def get_schedule(date: str, db: PlannerDB = Depends(get_db)):
    return {"date": date, "blocks": []}
