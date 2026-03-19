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
    if canvas_scraper is None:
        return {"error": "Canvas scraper not initialized"}
    config_id = canvas_scraper.launch_login(canvas_url)
    if config_id is None:
        return {"error": "Login timed out or failed"}
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
