import json
import threading
from fastapi import APIRouter, Depends, BackgroundTasks

from src.planner.db import PlannerDB

router = APIRouter(prefix="/canvas")

canvas_scraper = None

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/configs")
def list_configs(db: PlannerDB = Depends(get_db)):
    configs = db.list_canvas_configs()
    return [
        {"id": c["id"], "canvas_url": c["canvas_url"], "status": c["status"], "last_sync": c["last_sync"]}
        for c in configs
    ]

@router.post("/setup")
def setup_canvas(canvas_url: str, db: PlannerDB = Depends(get_db)):
    """Register a Canvas URL. Paste cookies separately to authenticate."""
    # Just register the URL with a placeholder — cookies will be pasted later
    config_id = db.add_canvas_config(canvas_url.strip(), "pending")
    db.update_canvas_status(config_id, "expired")  # Mark as needing cookies
    return {"status": "ok", "config_id": config_id}

@router.post("/relogin/{config_id}")
def relogin_canvas(config_id: int, db: PlannerDB = Depends(get_db)):
    if canvas_scraper is None:
        return {"error": "Canvas scraper not initialized"}
    success = canvas_scraper.relogin(config_id)
    return {"status": "ok" if success else "failed"}

@router.delete("/configs/{config_id}")
def delete_config(config_id: int, db: PlannerDB = Depends(get_db)):
    tasks = db.get_tasks(source="canvas")
    for task in tasks:
        db.update_task_status(task["id"], "skipped")
    db.soft_delete_canvas_config(config_id)
    return {"status": "deleted"}


@router.post("/cookies/{config_id}")
def paste_cookies(config_id: int, body: dict, db: PlannerDB = Depends(get_db)):
    """Update Canvas cookies from browser paste. Triggers immediate sync."""
    cookies_json = body.get("cookies", "")
    if not cookies_json:
        return {"error": "No cookies provided"}
    try:
        cookies = json.loads(cookies_json) if isinstance(cookies_json, str) else cookies_json
        from src.planner.encryption import EncryptionManager
        encryption = EncryptionManager()
        encrypted = encryption.encrypt(json.dumps(cookies))
        db.update_canvas_cookies(config_id, encrypted)
        db.update_canvas_status(config_id, "active")
        # Trigger immediate sync in background so grades populate right away
        if canvas_scraper:
            threading.Thread(target=_sync_config_bg, args=(config_id,), daemon=True).start()
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


def _sync_config_bg(config_id: int):
    """Background sync for a single Canvas config."""
    try:
        count = canvas_scraper.sync_config(config_id)
        import logging
        logging.getLogger(__name__).info("Immediate Canvas sync after cookie paste: %d items for config %d", count, config_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Immediate Canvas sync failed for config %d: %s", config_id, e)
