from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/preferences")
def get_preferences(db: PlannerDB = Depends(get_db)):
    return db.get_all_preferences()


@router.patch("/preferences")
def update_preferences(prefs: dict[str, str], db: PlannerDB = Depends(get_db)):
    for key, value in prefs.items():
        db.set_preference(key, value)
    return {"status": "updated", "count": len(prefs)}
