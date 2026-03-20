import json
import logging
import re
import requests
from datetime import datetime, timezone

from src.planner.db import PlannerDB
from src.planner.encryption import EncryptionManager
from src.planner.ingestion.canvas_parser import CanvasParser

logger = logging.getLogger(__name__)


class CanvasRequestsScraper:
    """Scrape Canvas using requests + stored cookies (no Playwright)."""

    def __init__(self, db: PlannerDB, encryption: EncryptionManager):
        self._db = db
        self._encryption = encryption

    def sync_config(self, config_id: int) -> int:
        config = self._db.get_canvas_config(config_id)
        if not config or config["status"] != "active":
            return 0

        canvas_url = config["canvas_url"].rstrip("/")
        try:
            cookies_raw = self._encryption.decrypt(config["session_cookies"])
            cookies_list = json.loads(cookies_raw)
        except Exception:
            logger.error("Failed to decrypt cookies for config %d", config_id)
            self._db.update_canvas_status(config_id, "error")
            return 0

        session = requests.Session()
        # Convert cookie list to requests cookies
        for cookie in cookies_list:
            session.cookies.set(
                cookie.get("name", ""),
                cookie.get("value", ""),
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )

        # Verify session by checking courses page
        resp = session.get(f"{canvas_url}/courses", allow_redirects=False, timeout=30)
        if resp.status_code in (301, 302, 303) and "login" in resp.headers.get("Location", "").lower():
            self._db.update_canvas_status(config_id, "expired")
            logger.warning("Canvas session expired for config %d", config_id)
            return 0

        parser = CanvasParser(canvas_url)
        total = 0

        # Extract courses
        courses_html = resp.text if resp.status_code == 200 else ""
        courses = parser.extract_course_list(courses_html)

        # Filter to current semester
        current_markers = ["sp26", "spring 2026", "spr26"]
        filtered = [c for c in courses if any(m in c["name"].lower() for m in current_markers)]
        if filtered:
            courses = filtered

        for course in courses:
            course_id = course["id"]
            course_name = course["name"]

            code_match = re.search(r'-\s*(.+?)(?:\s*\(\d+\))?$', course_name)
            course_code = code_match.group(1).strip() if code_match else course_name

            # Scrape assignments
            try:
                resp = session.get(f"{canvas_url}/courses/{course_id}/assignments", timeout=30)
                if resp.status_code == 200:
                    assignments = parser.parse_assignments_page(resp.text, course_id, course_name)
                    for a in assignments:
                        self._db.upsert_task(
                            source="canvas", external_id=a["external_id"],
                            title=a["title"], course=a["course"], deadline=a.get("due_date"),
                        )
                        total += 1
            except Exception as e:
                logger.warning("Failed assignments for %s: %s", course_name, e)

            # Scrape grades
            try:
                resp = session.get(f"{canvas_url}/courses/{course_id}/grades", timeout=30)
                if resp.status_code == 200:
                    grade_info = parser.parse_grades_page(resp.text, course_id)
                    # Save course
                    self._db.upsert_course(
                        canvas_course_id=course_id, name=course_name, code=course_code,
                        canvas_config_id=config_id,
                    )
                    if grade_info["current_grade"]:
                        conn = self._db._get_conn()
                        cursor = conn.execute("SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,))
                        row = cursor.fetchone()
                        if row:
                            self._db.update_course_grade(row[0], grade_info["current_grade"])
            except Exception as e:
                logger.warning("Failed grades for %s: %s", course_name, e)

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_canvas_last_sync(config_id, now)
        return total
