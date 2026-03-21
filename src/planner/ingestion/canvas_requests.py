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

    def _find_syllabus(self, session, api_url, canvas_url, course_id):
        """Search multiple locations for a course syllabus. Returns (url, text)."""
        syllabus_url = None
        syllabus_text = None

        # 1. Check syllabus_body from course API (most common)
        try:
            resp = session.get(
                f"{api_url}/courses/{course_id}",
                params={"include[]": "syllabus_body"},
                timeout=15,
            )
            if resp.status_code == 200:
                body = resp.json().get("syllabus_body", "") or ""
                if body.strip():
                    syllabus_text = body
                    # Extract external links from HTML
                    links = re.findall(r'href="([^"]+)"', body)
                    for link in links:
                        if link.startswith("http"):
                            syllabus_url = link
                            break
                    # If text is just a link, use it
                    if not syllabus_url:
                        import html as html_mod
                        text = re.sub(r'<[^>]+>', '', html_mod.unescape(body)).strip()
                        if text.startswith("http"):
                            syllabus_url = text.split()[0]
                        syllabus_text = text
        except Exception as e:
            logger.debug("Syllabus body check failed: %s", e)

        # 2. Search files for syllabus PDFs
        if not syllabus_url:
            try:
                resp = session.get(
                    f"{api_url}/courses/{course_id}/files",
                    params={"search_term": "syllabus", "per_page": "10"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    files = resp.json()
                    for f in files:
                        name = f.get("display_name", "").lower()
                        if "syllabus" in name:
                            syllabus_url = f.get("url", "")
                            if not syllabus_text:
                                syllabus_text = f.get("display_name", "")
                            break
            except Exception as e:
                logger.debug("Syllabus files check failed: %s", e)

        # 3. Search files for schedule PDFs (some courses call it "schedule" not "syllabus")
        if not syllabus_url:
            try:
                resp = session.get(
                    f"{api_url}/courses/{course_id}/files",
                    params={"search_term": "schedule", "per_page": "10"},
                    timeout=15,
                )
                if resp.status_code == 200:
                    files = resp.json()
                    for f in files:
                        name = f.get("display_name", "").lower()
                        if "schedule" in name or "outline" in name:
                            syllabus_url = f.get("url", "")
                            if not syllabus_text:
                                syllabus_text = f.get("display_name", "")
                            break
            except Exception as e:
                logger.debug("Schedule files check failed: %s", e)

        # 4. Check front page / home page for syllabus links
        if not syllabus_url:
            try:
                resp = session.get(
                    f"{api_url}/courses/{course_id}/front_page",
                    timeout=15,
                )
                if resp.status_code == 200:
                    body = resp.json().get("body", "") or ""
                    links = re.findall(r'href="([^"]+)"', body)
                    for link in links:
                        if "syllabus" in link.lower():
                            syllabus_url = link
                            break
            except Exception as e:
                logger.debug("Front page check failed: %s", e)

        return syllabus_url, syllabus_text

    def _download_syllabus(self, session, syllabus_url, course_id, api_url):
        """Download syllabus file and save locally. Returns local filename or None."""
        import os, re
        save_dir = os.path.join(os.path.dirname(self._db.db_path), "syllabi")
        os.makedirs(save_dir, exist_ok=True)

        try:
            # If it's a Canvas file viewer URL, get direct download via API
            file_match = re.search(r'/files/(\d+)', syllabus_url)
            if file_match and 'instructure.com' in syllabus_url:
                fid = file_match.group(1)
                r = session.get(f"{api_url}/files/{fid}", timeout=15)
                if r.status_code == 200:
                    direct_url = r.json().get("url")
                    if direct_url:
                        syllabus_url = direct_url

            # Download the content
            r = session.get(syllabus_url, timeout=30, allow_redirects=True)
            if r.status_code != 200:
                return None

            ct = r.headers.get("content-type", "")
            if "pdf" in ct or r.content[:5] == b"%PDF-":
                fname = f"syllabus_{course_id}.pdf"
                with open(os.path.join(save_dir, fname), "wb") as f:
                    f.write(r.content)
                return fname
            elif "html" in ct:
                fname = f"syllabus_{course_id}.html"
                with open(os.path.join(save_dir, fname), "w", encoding="utf-8") as f:
                    f.write(r.text)
                return fname
        except Exception as e:
            logger.warning("Failed to download syllabus: %s", e)
        return None

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

            # Find syllabus
            syllabus_url = None
            syllabus_text = None
            try:
                syllabus_url, syllabus_text = self._find_syllabus(
                    session, api_url, canvas_url, course_id
                )
            except Exception as e:
                logger.warning("Failed syllabus for %s: %s", course_name, e)

            # Download syllabus file locally
            syllabus_file = None
            if syllabus_url:
                syllabus_file = self._download_syllabus(
                    session, syllabus_url, course_id, api_url
                )

            # Save course
            self._db.upsert_course(
                canvas_course_id=course_id, name=course_name, code=course_code,
                syllabus_url=syllabus_url, syllabus_text=syllabus_text,
                syllabus_file=syllabus_file,
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
