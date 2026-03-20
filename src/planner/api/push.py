import os

from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api/push")

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.get("/vapid-key")
def get_vapid_key():
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe")
def subscribe(body: dict, db: PlannerDB = Depends(get_db)):
    endpoint = body.get("endpoint", "")
    keys = body.get("keys", {})
    p256dh = keys.get("p256dh", "")
    auth = keys.get("auth", "")
    if not endpoint or not p256dh or not auth:
        return {"error": "Invalid subscription"}
    db.add_push_subscription(endpoint, p256dh, auth)
    return {"status": "subscribed"}


@router.delete("/subscribe")
def unsubscribe(body: dict, db: PlannerDB = Depends(get_db)):
    endpoint = body.get("endpoint", "")
    db.remove_push_subscription(endpoint)
    return {"status": "unsubscribed"}
