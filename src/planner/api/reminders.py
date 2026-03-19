from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/reminders")
def list_reminders(db: PlannerDB = Depends(get_db)):
    return db.get_pending_reminders()


@router.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    action = body.get("action", "dismiss")
    if action == "dismiss":
        db.mark_reminder_fired(reminder_id)
    return {"status": "ok"}
