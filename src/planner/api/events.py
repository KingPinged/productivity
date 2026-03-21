import secrets
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

@router.post("/events")
def create_event(body: dict, db: PlannerDB = Depends(get_db)):
    """Create a new calendar event."""
    eid = db.upsert_event(
        account_id=None,
        source="manual",
        external_id=f"manual:{secrets.token_urlsafe(8)}",
        title=body.get("title", "New Event"),
        start_time=body.get("start_time"),
        end_time=body.get("end_time"),
        event_type=body.get("event_type", "personal"),
        all_day=body.get("all_day", False),
        description=body.get("description"),
    )
    return {"id": eid, "status": "created"}

@router.patch("/events/{event_id}")
def update_event(event_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    """Update an existing event (title, times, etc)."""
    conn = db._get_conn()
    # Build update query dynamically
    fields = []
    params = []
    for key in ["title", "start_time", "end_time", "event_type", "description"]:
        if key in body:
            fields.append(f"{key} = ?")
            params.append(body[key])
    if not fields:
        return {"status": "no changes"}
    params.append(event_id)
    conn.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ?", params)
    conn.commit()
    return {"status": "updated"}

@router.delete("/events/{event_id}")
def delete_event(event_id: int, db: PlannerDB = Depends(get_db)):
    """Delete a calendar event."""
    conn = db._get_conn()
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    return {"status": "deleted"}
