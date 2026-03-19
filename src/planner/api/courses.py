from fastapi import APIRouter, Depends
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/courses")
def list_courses(db: PlannerDB = Depends(get_db)):
    """List all courses with syllabus info."""
    return db.get_courses()

@router.get("/courses/{course_id}")
def get_course(course_id: int, db: PlannerDB = Depends(get_db)):
    """Get a single course with full details."""
    course = db.get_course(course_id)
    if not course:
        return {"error": "Course not found"}
    # Also get tasks for this course
    tasks = db.get_tasks(source="canvas")
    course_tasks = [t for t in tasks if t.get("course") == course["name"]]
    return {**course, "tasks": course_tasks}
