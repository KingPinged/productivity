import json
import logging
import re
import requests
from datetime import datetime, timezone

from src.planner.db import PlannerDB
from src.planner.encryption import EncryptionManager

logger = logging.getLogger(__name__)


class CanvasRequestsScraper:
    """Scrape Canvas using REST API + stored cookies (no Playwright)."""

    def __init__(self, db: PlannerDB, encryption: EncryptionManager):
        self._db = db
        self._encryption = encryption

    def _make_session(self, config):
        """Create a requests session with decrypted cookies."""
        cookies_raw = self._encryption.decrypt(config["session_cookies"])
        cookies_list = json.loads(cookies_raw)
        session = requests.Session()
        for cookie in cookies_list:
            session.cookies.set(
                cookie.get("name", ""),
                cookie.get("value", ""),
                domain=cookie.get("domain", ""),
                path=cookie.get("path", "/"),
            )
        return session

    def _api_get(self, session, url, params=None):
        """Make a Canvas API request, handling pagination."""
        all_items = []
        while url:
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 401:
                return None  # Session expired
            if resp.status_code != 200:
                break
            all_items.extend(resp.json())
            # Handle pagination via Link header
            link = resp.headers.get("Link", "")
            url = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split("<")[1].split(">")[0]
                    params = None  # URL already has params
            if len(all_items) > 500:
                break  # Safety limit
        return all_items

    def sync_config(self, config_id: int) -> int:
        config = self._db.get_canvas_config(config_id)
        if not config or config["status"] != "active":
            return 0

        canvas_url = config["canvas_url"].rstrip("/")
        api_url = f"{canvas_url}/api/v1"

        try:
            session = self._make_session(config)
        except Exception:
            logger.error("Failed to decrypt cookies for config %d", config_id)
            self._db.update_canvas_status(config_id, "error")
            return 0

        # Get active courses via API
        courses = self._api_get(session, f"{api_url}/courses",
                                {"enrollment_state": "active", "per_page": "50"})
        if courses is None:
            self._db.update_canvas_status(config_id, "expired")
            logger.warning("Canvas session expired for config %d", config_id)
            return 0

        # Filter to current semester
        current_markers = ["sp26", "spring 2026", "spr26"]
        filtered = [c for c in courses if any(m in c.get("name", "").lower() for m in current_markers)]
        if filtered:
            courses = filtered

        total = 0

        for course in courses:
            course_id = str(course["id"])
            course_name = course.get("name", "Unknown")

            code_match = re.search(r'-\s*(.+?)(?:\s*\(\d+\))?$', course_name)
            course_code = code_match.group(1).strip() if code_match else course_name

            # Save course
            self._db.upsert_course(
                canvas_course_id=course_id, name=course_name, code=course_code,
                canvas_config_id=config_id,
            )

            # Get assignments via API
            try:
                assignments = self._api_get(
                    session, f"{api_url}/courses/{course_id}/assignments",
                    {"per_page": "50", "order_by": "due_at"}
                )
                if assignments:
                    for a in assignments:
                        aid = str(a.get("id", ""))
                        title = a.get("name", "Untitled")
                        due_at = a.get("due_at")  # Already ISO format from API

                        self._db.upsert_task(
                            source="canvas",
                            external_id=f"canvas:{course_id}:{aid}",
                            title=title,
                            course=course_name,
                            deadline=due_at,
                        )
                        total += 1
            except Exception as e:
                logger.warning("Failed assignments for %s: %s", course_name, e)

            # Get grades via API
            try:
                enrollments = self._api_get(
                    session, f"{api_url}/courses/{course_id}/enrollments",
                    {"user_id": "self", "per_page": "5"}
                )
                if enrollments:
                    for enr in enrollments:
                        grades = enr.get("grades", {})
                        current_grade = grades.get("current_score")
                        letter = grades.get("current_grade")
                        if current_grade or letter:
                            grade_str = f"{current_grade}%" if current_grade else ""
                            if letter:
                                grade_str = f"{letter} ({grade_str})" if grade_str else letter
                            conn = self._db._get_conn()
                            cursor = conn.execute("SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,))
                            row = cursor.fetchone()
                            if row:
                                self._db.update_course_grade(row[0], grade_str)
                            break
            except Exception as e:
                logger.warning("Failed grades for %s: %s", course_name, e)

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_canvas_last_sync(config_id, now)
        return total
