import html
import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.planner.db import PlannerDB
from src.planner.ingestion.syllabus_parser import (
    parse_syllabus_for_course,
    map_assignment_to_category,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


class CategoryUpdate(BaseModel):
    name: str
    weight: float


class CategoriesBody(BaseModel):
    categories: list[CategoryUpdate]


class ScaleEntry(BaseModel):
    letter: str
    min_percent: float
    max_percent: float | None = None


class ScaleBody(BaseModel):
    scale: list[ScaleEntry]


class SimulationOverride(BaseModel):
    grade_id: int | None = None
    category: str | None = None
    name: str | None = None
    score: str
    points_possible: str | None = None


class SimulateBody(BaseModel):
    overrides: list[SimulationOverride]


def _compute_grade(categories: list[dict], grades: list[dict], grade_scale: list[dict],
                   overrides: list[dict] | None = None) -> dict:
    """Core grade computation. Groups assignments by category, computes weighted grade."""
    # Build override map: grade_id -> score
    override_map: dict[int, float] = {}
    extra_assignments: list[dict] = []
    if overrides:
        for ov in overrides:
            if ov.get("grade_id"):
                override_map[ov["grade_id"]] = float(ov["score"])
            else:
                extra_assignments.append(ov)

    # Group assignments by category
    cat_data: dict[str, dict] = {}
    for cat in categories:
        cat_data[cat["name"]] = {
            "name": cat["name"],
            "weight": cat["weight"],
            "earned": 0.0,
            "possible": 0.0,
            "assignments": [],
        }

    # Ensure "Uncategorized" bucket exists
    if "Uncategorized" not in cat_data:
        cat_data["Uncategorized"] = {
            "name": "Uncategorized",
            "weight": 0.0,
            "earned": 0.0,
            "possible": 0.0,
            "assignments": [],
        }

    for g in grades:
        cat_name = g.get("category") or "Uncategorized"
        if cat_name not in cat_data:
            cat_data[cat_name] = {
                "name": cat_name,
                "weight": 0.0,
                "earned": 0.0,
                "possible": 0.0,
                "assignments": [],
            }

        score_str = g.get("score")
        possible_str = g.get("points_possible")

        # Apply override if exists
        if g["id"] in override_map:
            score_val = override_map[g["id"]]
        elif score_str and score_str.strip():
            try:
                score_val = float(score_str)
            except ValueError:
                score_val = None
        else:
            score_val = None

        try:
            possible_val = float(possible_str) if possible_str else None
        except ValueError:
            possible_val = None

        cat_data[cat_name]["assignments"].append({
            "id": g["id"],
            "name": g["assignment_name"],
            "score": str(score_val) if score_val is not None else None,
            "points_possible": possible_str,
            "category": cat_name,
        })

        if score_val is not None and possible_val and possible_val > 0:
            cat_data[cat_name]["earned"] += score_val
            cat_data[cat_name]["possible"] += possible_val

    # Add extra hypothetical assignments
    for ea in extra_assignments:
        cat_name = ea.get("category", "Uncategorized")
        if cat_name not in cat_data:
            continue
        score_val = float(ea["score"])
        possible_val = float(ea.get("points_possible", "100"))
        cat_data[cat_name]["assignments"].append({
            "id": None,
            "name": ea.get("name", "Hypothetical"),
            "score": ea["score"],
            "points_possible": ea.get("points_possible", "100"),
            "category": cat_name,
            "hypothetical": True,
        })
        if possible_val > 0:
            cat_data[cat_name]["earned"] += score_val
            cat_data[cat_name]["possible"] += possible_val

    # Compute per-category scores
    result_categories = []
    for cat in cat_data.values():
        cat["score"] = round(cat["earned"] / cat["possible"] * 100, 2) if cat["possible"] > 0 else None
        result_categories.append(cat)

    # Remove empty Uncategorized
    result_categories = [c for c in result_categories if c["assignments"] or c["name"] != "Uncategorized"]

    # Compute weighted grade (normalized by active weight sum)
    active_weight_sum = 0.0
    weighted_sum = 0.0
    for cat in result_categories:
        if cat["weight"] > 0 and cat["score"] is not None:
            weighted_sum += cat["score"] * cat["weight"] / 100.0
            active_weight_sum += cat["weight"]

    if active_weight_sum > 0:
        weighted_grade = round(weighted_sum / active_weight_sum * 100, 2)
    else:
        # Fallback: simple average of all graded assignments
        total_earned = sum(c["earned"] for c in result_categories)
        total_possible = sum(c["possible"] for c in result_categories)
        weighted_grade = round(total_earned / total_possible * 100, 2) if total_possible > 0 else None

    # Map to letter grade
    letter_grade = None
    if weighted_grade is not None and grade_scale:
        for entry in sorted(grade_scale, key=lambda x: x["min_percent"], reverse=True):
            if weighted_grade >= entry["min_percent"]:
                letter_grade = entry["letter"]
                break

    return {
        "categories": result_categories,
        "weightedGrade": weighted_grade,
        "letterGrade": letter_grade,
        "gradeScale": [
            {"letter": s["letter"], "minPercent": s["min_percent"], "maxPercent": s.get("max_percent")}
            for s in grade_scale
        ],
    }


@router.get("/courses/{course_id}/grade-calculator")
def get_grade_calculator(course_id: int, db: PlannerDB = Depends(get_db)):
    categories = db.get_grade_categories(course_id)
    grades = db.get_grades_for_course(course_id)
    grade_scale = db.get_grade_scale(course_id)
    return _compute_grade(categories, grades, grade_scale)


@router.post("/courses/{course_id}/grade-calculator/simulate")
def simulate_grades(course_id: int, body: SimulateBody, db: PlannerDB = Depends(get_db)):
    categories = db.get_grade_categories(course_id)
    grades = db.get_grades_for_course(course_id)
    grade_scale = db.get_grade_scale(course_id)
    overrides = [ov.model_dump() for ov in body.overrides]
    return _compute_grade(categories, grades, grade_scale, overrides=overrides)


@router.put("/courses/{course_id}/grade-categories")
def update_grade_categories(course_id: int, body: CategoriesBody, db: PlannerDB = Depends(get_db)):
    db.set_grade_categories(
        course_id,
        [{"name": c.name, "weight": c.weight} for c in body.categories],
        source="manual",
    )
    return {"ok": True}


class MoveGradeBody(BaseModel):
    category: str | None


@router.put("/grades/{grade_id}/category")
def move_grade_category(grade_id: int, body: MoveGradeBody, db: PlannerDB = Depends(get_db)):
    """Move an assignment to a different category."""
    db.update_grade_category(grade_id, body.category)
    return {"ok": True}


@router.delete("/grades/{grade_id}")
def delete_grade(grade_id: int, db: PlannerDB = Depends(get_db)):
    """Delete an assignment from grade tracking."""
    db.delete_grade(grade_id)
    return {"ok": True}


@router.put("/courses/{course_id}/grade-scale")
def update_grade_scale(course_id: int, body: ScaleBody, db: PlannerDB = Depends(get_db)):
    db.set_grade_scale(
        course_id,
        [{"letter": s.letter, "min_percent": s.min_percent, "max_percent": s.max_percent} for s in body.scale],
    )
    return {"ok": True}


def _extract_syllabus_text(course: dict, db: PlannerDB) -> str:
    """Extract plain text from syllabus file (PDF or HTML) or fall back to DB text."""
    syllabus_file = course.get("syllabus_file") or ""
    if syllabus_file:
        data_dir = os.path.dirname(db.db_path)
        file_path = os.path.join(data_dir, "syllabi", syllabus_file)
        if os.path.exists(file_path):
            if syllabus_file.endswith(".pdf"):
                try:
                    import pdfplumber
                    text_parts = []
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text_parts.append(page_text)
                    if text_parts:
                        return "\n".join(text_parts)
                except Exception as e:
                    logger.warning("PDF extraction failed for %s: %s", file_path, e)
            elif syllabus_file.endswith(".html"):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        raw = f.read()
                    # Strip HTML tags, decode entities
                    text = re.sub(r"<[^>]+>", " ", raw)
                    text = html.unescape(text)
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        return text
                except Exception as e:
                    logger.warning("HTML extraction failed for %s: %s", file_path, e)

    # Fall back to DB syllabus_text field
    return course.get("syllabus_text") or ""


@router.post("/courses/{course_id}/reparse-syllabus")
def reparse_syllabus(course_id: int, db: PlannerDB = Depends(get_db)):
    course = db.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    syllabus_text = _extract_syllabus_text(course, db)
    if not syllabus_text.strip():
        raise HTTPException(status_code=400, detail="No syllabus text available")

    logger.info("Parsing syllabus for course %d (%s), text length: %d", course_id, course.get("code"), len(syllabus_text))
    parsed = parse_syllabus_for_course(syllabus_text)

    # Delete existing auto-parsed entries, keep manual
    db.delete_auto_grade_categories(course_id)
    db.set_grade_scale(course_id, [])

    for w in parsed["grade_weights"]:
        weight_num = float(w["weight"].replace("%", ""))
        db.upsert_grade_category(course_id, w["category"], weight_num, source="auto")

    for s in parsed["grade_scale"]:
        db.upsert_grade_scale(course_id, s["letter"], s["min_percent"], s.get("max_percent"))

    # Re-map assignments to categories
    categories = db.get_grade_categories(course_id)
    cat_names = [c["name"] for c in categories]
    grades = db.get_grades_for_course(course_id)
    for g in grades:
        matched = map_assignment_to_category(g["assignment_name"], cat_names)
        if matched:
            db.update_grade_category(g["id"], matched)

    return {"ok": True, "parsed": True, "weights": len(parsed["grade_weights"]), "scale": len(parsed["grade_scale"])}
