import os
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

# Separate router for syllabus files — no auth needed (served to iframes)
public_router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

@router.get("/courses")
def list_courses(db: PlannerDB = Depends(get_db)):
    """List all courses with syllabus info."""
    return db.get_courses()

@public_router.get("/courses/{course_id}/syllabus-file")
def get_syllabus_file(course_id: int, db: PlannerDB = Depends(get_db)):
    """Serve the locally stored syllabus file."""
    course = db.get_course(course_id)
    if not course or not course.get("syllabus_file"):
        return {"error": "No syllabus file available"}

    data_dir = os.path.dirname(db.db_path)
    file_path = os.path.join(data_dir, "syllabi", course["syllabus_file"])

    if not os.path.exists(file_path):
        return {"error": "File not found"}

    media_type = "application/pdf" if file_path.endswith(".pdf") else "text/html"
    return FileResponse(file_path, media_type=media_type)


@router.get("/courses/{course_id}")
def get_course(course_id: int, db: PlannerDB = Depends(get_db)):
    """Get a single course with full details."""
    course = db.get_course(course_id)
    if not course:
        return {"error": "Course not found"}
    # Also get tasks for this course
    tasks = db.get_tasks(source="canvas")
    course_tasks = [t for t in tasks if t.get("course") == course["name"]]
    grades = db.get_grades_for_course(course_id)
    return {**course, "tasks": course_tasks, "grades": grades}


@router.get("/grades")
def get_grades_summary(db: PlannerDB = Depends(get_db)):
    courses = db.get_courses()
    result = []
    for c in courses:
        grades = db.get_grades_for_course(c["id"])
        result.append({
            "course_id": c["id"],
            "course_name": c["name"],
            "course_code": c["code"],
            "current_grade": c.get("current_grade"),
            "total_assignments": len(grades),
            "graded": len([g for g in grades if g["score"]]),
        })
    return result
