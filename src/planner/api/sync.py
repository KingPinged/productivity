from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/sync")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

sync_callback = None

@router.get("/status")
def sync_status(db: PlannerDB = Depends(get_db)):
    accounts = db.list_accounts()
    return {
        "accounts": [
            {"email": a["email"], "last_sync": a["last_sync"], "provider": a["provider"]}
            for a in accounts
        ]
    }

@router.post("/trigger")
def trigger_sync(db: PlannerDB = Depends(get_db)):
    if sync_callback:
        sync_callback()
    return {"status": "triggered"}
