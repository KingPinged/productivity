from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

ai_scheduler = None

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/schedule/{date}")
def get_schedule(date: str, db: PlannerDB = Depends(get_db)):
    blocks = db.get_schedule_blocks(date)
    return {"date": date, "blocks": blocks}

@router.patch("/schedule/{block_id}")
def update_block(block_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    if "status" in body:
        db.update_block_status(block_id, body["status"])
    return {"status": "updated"}

@router.post("/schedule/replan")
def trigger_replan(body: dict | None = None, db: PlannerDB = Depends(get_db)):
    from datetime import date as date_type
    target_date = (body or {}).get("date", date_type.today().isoformat())
    if ai_scheduler is None:
        return {"error": "AI scheduler not configured. Set anthropic_api_key in preferences."}
    result = ai_scheduler.replan(target_date)
    if result is None:
        return {"status": "failed", "message": "AI scheduling failed. Check API key and try again."}
    ai_scheduler.store_schedule(target_date, result)
    return {
        "status": "ok",
        "blocks_count": len(result.get("schedule", [])),
        "summary": result.get("summary", ""),
        "email_alerts": result.get("email_alerts", []),
        "tasks_today": result.get("tasks_today", []),
        "tasks_later": result.get("tasks_later", []),
    }


@router.post("/context")
def add_context(body: dict, db: PlannerDB = Depends(get_db)):
    """Add user context message for AI scheduling."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Message is required"}
    ctx_id = db.add_user_context(message)
    return {"status": "ok", "id": ctx_id}

@router.get("/context")
def get_context(db: PlannerDB = Depends(get_db)):
    """Get active user context messages."""
    return db.get_active_context()

@router.delete("/context")
def clear_context(db: PlannerDB = Depends(get_db)):
    """Clear all user context messages."""
    db.clear_context()
    return {"status": "cleared"}
