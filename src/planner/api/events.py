import logging
import re
import secrets
from fastapi import APIRouter, Depends, Query
from src.planner.db import PlannerDB

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")

# Keywords that indicate an important date (exam, deadline, etc.)
# "final" alone is too broad — require "final exam" or "final project"
IMPORTANT_KEYWORDS = re.compile(
    r"\b(exam\s*\d*|midterm|mid-?term|final\s+exam|final\s+project|presentation\s+day|project\s+due|paper\s+due)\b",
    re.IGNORECASE,
)

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


@router.post("/events/extract-important-dates")
def extract_important_dates(db: PlannerDB = Depends(get_db)):
    """Scan Canvas tasks and syllabus for exams, finals, midterms, etc.
    Creates high-priority calendar events with descriptions."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    tasks = db.get_tasks()
    courses = {c["id"]: c for c in db.get_courses()}
    created = []

    for task in tasks:
        title = task.get("title", "")
        deadline = task.get("deadline")
        if not deadline or not IMPORTANT_KEYWORDS.search(title):
            continue
        # Skip past events
        if deadline < now:
            continue

        # Build description with course context
        course_name = task.get("course") or ""
        desc_parts = []
        if course_name:
            desc_parts.append(f"Course: {course_name}")
        desc_parts.append(f"Source: {task.get('source', 'unknown')}")
        if task.get("estimated_minutes"):
            desc_parts.append(f"Estimated time: {task['estimated_minutes']} min")
        if task.get("grade_weight"):
            desc_parts.append(f"Grade weight: {task['grade_weight']}")
        desc_parts.append(f"Priority: HIGH - auto-detected from '{title}'")
        description = "\n".join(desc_parts)

        # Use external_id to prevent duplicates
        ext_id = f"important:{task.get('source', 'manual')}:{task.get('id', title)}"

        eid = db.upsert_event(
            account_id=None,
            source="manual",
            external_id=ext_id,
            title=f"\u26A0 {title}",
            start_time=deadline,
            end_time=deadline,
            event_type="meeting",
            all_day=False,
            description=description,
        )
        if eid != 0:
            created.append({"title": title, "date": deadline, "course": course_name})
            logger.info("Created important event: %s on %s", title, deadline)

    # Also scan syllabus text for date patterns with exam keywords
    for course_id, course in courses.items():
        syllabus_text = _get_syllabus_text(course, db)
        if not syllabus_text:
            continue
        exam_dates = _extract_exam_dates_from_text(syllabus_text, course.get("code") or course.get("name") or "")
        for ed in exam_dates:
            ext_id = f"syllabus-exam:{course_id}:{ed['title']}"
            eid = db.upsert_event(
                account_id=None,
                source="manual",
                external_id=ext_id,
                title=f"\u26A0 {ed['title']}",
                start_time=ed["date"],
                event_type="meeting",
                all_day=True,
                description=f"Course: {course.get('code') or course.get('name')}\nSource: syllabus\nPriority: HIGH - extracted from syllabus",
            )
            if eid != 0:
                created.append({"title": ed["title"], "date": ed["date"], "course": course.get("code")})

    return {"status": "ok", "created": len(created), "events": created}


def _get_syllabus_text(course: dict, db: PlannerDB) -> str:
    """Extract text from syllabus PDF/HTML file."""
    import os
    syllabus_file = course.get("syllabus_file") or ""
    if syllabus_file:
        data_dir = os.path.dirname(db.db_path)
        file_path = os.path.join(data_dir, "syllabi", syllabus_file)
        if os.path.exists(file_path):
            if syllabus_file.endswith(".pdf"):
                try:
                    import pdfplumber
                    parts = []
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            t = page.extract_text()
                            if t:
                                parts.append(t)
                    return "\n".join(parts)
                except Exception:
                    pass
            elif syllabus_file.endswith(".html"):
                try:
                    import html as html_mod
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        raw = f.read()
                    text = re.sub(r"<[^>]+>", " ", raw)
                    return html_mod.unescape(text)
                except Exception:
                    pass
    return course.get("syllabus_text") or ""


def _extract_exam_dates_from_text(text: str, course_code: str) -> list[dict]:
    """Extract exam dates from syllabus text. Returns [{"title": str, "date": str}]."""
    results = []
    # Common patterns: "Exam 1: March 5", "Midterm: 3/5/2026", "Final Exam - April 30, 2026"
    date_patterns = [
        # "March 5, 2026" or "March 5"
        r"((?:exam|midterm|mid-?term|final|final\s+exam|test|quiz)\s*\d*)\s*[:=\-\u2013]\s*"
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:,?\s*\d{4})?)",
        # "3/5/2026" or "03/05/26"
        r"((?:exam|midterm|mid-?term|final|final\s+exam|test|quiz)\s*\d*)\s*[:=\-\u2013]\s*"
        r"(\d{1,2}/\d{1,2}/\d{2,4})",
    ]

    for pattern in date_patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            title = f"{course_code} {m.group(1).strip()}"
            date_str = m.group(2).strip()
            # Try to normalize to ISO format
            iso_date = _parse_date_str(date_str)
            if iso_date:
                results.append({"title": title, "date": iso_date})

    return results


def _parse_date_str(date_str: str) -> str | None:
    """Try to parse a date string into YYYY-MM-DD format."""
    from datetime import datetime
    formats = [
        "%B %d, %Y", "%B %d %Y", "%B %d",
        "%m/%d/%Y", "%m/%d/%y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # If no year, assume current year
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None
