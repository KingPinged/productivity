import secrets
from fastapi import APIRouter, Depends, Query
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/tasks")
def list_tasks(
    source: str | None = Query(None),
    status: str | None = Query(None),
    db: PlannerDB = Depends(get_db),
):
    return db.get_tasks(source=source, status=status)

@router.post("/tasks")
def create_task(body: dict, db: PlannerDB = Depends(get_db)):
    task_id = db.upsert_task(
        source="manual",
        external_id=f"manual:{secrets.token_urlsafe(8)}",
        title=body.get("title", "Untitled"),
        description=body.get("description"),
        course=body.get("course"),
        deadline=body.get("deadline"),
        estimated_minutes=body.get("estimated_minutes"),
        priority=body.get("priority", 3),
    )
    return {"task_id": task_id}

@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    if "status" in body:
        db.update_task_status(task_id, body["status"])
    return {"status": "updated"}

@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: PlannerDB = Depends(get_db)):
    db.update_task_status(task_id, "skipped")
    return {"status": "deleted"}
