import json
import logging
import time

from src.planner.db import PlannerDB
from src.planner.encryption import EncryptionManager
from src.planner.ingestion.canvas_parser import CanvasParser

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 30


class CanvasScraper:
    """Scrape Canvas LMS using Playwright with saved session cookies."""

    def __init__(self, db: PlannerDB, encryption: EncryptionManager):
        self._db = db
        self._encryption = encryption

    def launch_login(self, canvas_url: str) -> int | None:
        """Open a headed browser for manual login. Returns config_id or None."""
        from playwright.sync_api import sync_playwright

        canvas_url = canvas_url.rstrip("/")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(canvas_url)
            logger.info("Waiting for user to log in to Canvas at %s ...", canvas_url)
            try:
                page.wait_for_url("**/courses**", timeout=300_000)
            except Exception:
                try:
                    page.wait_for_selector("#global_nav_accounts_link", timeout=60_000)
                except Exception:
                    logger.error("Login timed out")
                    browser.close()
                    return None

            cookies = context.cookies()
            encrypted_cookies = self._encryption.encrypt(json.dumps(cookies))
            config_id = self._db.add_canvas_config(canvas_url, encrypted_cookies)

            browser.close()
            logger.info("Canvas login successful, config saved (id=%d)", config_id)
            return config_id

    def relogin(self, config_id: int) -> bool:
        """Re-authenticate an existing Canvas config. Returns True on success."""
        config = self._db.get_canvas_config(config_id)
        if not config:
            return False

        result_id = self.launch_login(config["canvas_url"])
        if result_id is None:
            return False

        if result_id != config_id:
            new_config = self._db.get_canvas_config(result_id)
            if new_config:
                self._db.update_canvas_cookies(config_id, new_config["session_cookies"])
                self._db.soft_delete_canvas_config(result_id)

        self._db.update_canvas_status(config_id, "active")
        return True

    def sync_config(self, config_id: int) -> int:
        """Scrape Canvas for a given config. Returns number of items synced."""
        config = self._db.get_canvas_config(config_id)
        if not config or config["status"] != "active":
            return 0

        canvas_url = config["canvas_url"]
        try:
            cookies = json.loads(self._encryption.decrypt(config["session_cookies"]))
        except Exception:
            logger.error("Failed to decrypt cookies for config %d", config_id)
            self._db.update_canvas_status(config_id, "error")
            return 0

        from playwright.sync_api import sync_playwright

        total = 0
        parser = CanvasParser(canvas_url)

        for attempt in range(MAX_RETRIES + 1):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies(cookies)

                try:
                    total = self._scrape_with_context(config_id, canvas_url, context, parser)
                    return total
                except _SessionExpiredError:
                    if attempt < MAX_RETRIES:
                        logger.info("Canvas session may be expired, retry %d/%d in %ds",
                                    attempt + 1, MAX_RETRIES, RETRY_DELAY)
                        browser.close()
                        time.sleep(RETRY_DELAY)
                        continue
                    self._db.update_canvas_status(config_id, "expired")
                    logger.warning("Canvas session expired for config %d after %d retries",
                                   config_id, MAX_RETRIES)
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        logger.info("Canvas scrape error, retry %d/%d: %s", attempt + 1, MAX_RETRIES, e)
                        browser.close()
                        time.sleep(RETRY_DELAY)
                        continue
                    logger.error("Canvas scrape failed for config %d: %s", config_id, e)
                finally:
                    browser.close()

        return total

    def _scrape_with_context(self, config_id, canvas_url, context, parser) -> int:
        """Scrape all Canvas pages using an authenticated browser context."""
        page = context.new_page()
        total = 0

        # Navigate to courses page to verify session
        page.goto(f"{canvas_url}/courses", wait_until="networkidle", timeout=30_000)
        if self._is_session_expired(page, canvas_url):
            raise _SessionExpiredError()

        # Scrape courses list
        courses_html = page.content()
        courses = parser.extract_course_list(courses_html)

        # Filter to likely current semester courses (contain "Sp26", "Spring 2026", etc.)
        # Also include courses without semester markers
        current_markers = ["sp26", "spring 2026", "spr26", "spring26"]
        filtered = [c for c in courses if any(m in c["name"].lower() for m in current_markers)]
        if filtered:
            courses = filtered
            logger.info("Filtered to %d current semester courses", len(courses))

        for course in courses:
            course_id = course["id"]
            course_name = course["name"]

            # Extract course code from name (e.g., "Sp26 - MOBILE COMPUTING (53365)" -> "MOBILE COMPUTING")
            import re
            code_match = re.search(r'-\s*(.+?)(?:\s*\(\d+\))?$', course_name)
            course_code = code_match.group(1).strip() if code_match else course_name

            # Scrape syllabus
            syllabus_url = None
            syllabus_text = None
            try:
                page.goto(
                    f"{canvas_url}/courses/{course_id}/assignments/syllabus",
                    wait_until="networkidle", timeout=30_000,
                )
                syl_el = page.query_selector('#course_syllabus')
                if syl_el:
                    syllabus_text = syl_el.inner_text().strip()
                    # Check for external syllabus links
                    syl_links = syl_el.query_selector_all('a')
                    for link in syl_links:
                        href = link.get_attribute('href') or ''
                        if href and ('syllabus' in href.lower() or href.startswith('http')):
                            syllabus_url = href
                            break
                    # If syllabus text is just a link, the URL is the syllabus
                    if not syllabus_url and syllabus_text and syllabus_text.startswith('http'):
                        syllabus_url = syllabus_text.split('\n')[0].strip()

                # Also check for syllabus file links on the syllabus page
                if not syllabus_url:
                    file_links = page.query_selector_all('a[href*="/files/"]')
                    for fl in file_links:
                        text = fl.inner_text().strip().lower()
                        href = fl.get_attribute('href') or ''
                        if 'syllabus' in text or 'syllabus' in href.lower():
                            syllabus_url = href
                            break
            except Exception as e:
                logger.warning("Failed to scrape syllabus for %s: %s", course_name, e)

            # If still no syllabus, check files page
            if not syllabus_url:
                try:
                    page.goto(
                        f"{canvas_url}/courses/{course_id}/files",
                        wait_until="networkidle", timeout=30_000,
                    )
                    files_html = page.content()
                    import re as re_mod
                    syl_files = re_mod.findall(
                        r'"url":"([^"]*)"[^}]*"display_name":"([^"]*[Ss]yllabus[^"]*)"',
                        files_html,
                    )
                    if syl_files:
                        syllabus_url = syl_files[0][0]
                except Exception as e:
                    logger.warning("Failed to check files for syllabus: %s", e)

            # Save course info
            self._db.upsert_course(
                canvas_course_id=course_id,
                name=course_name,
                code=course_code,
                syllabus_url=syllabus_url,
                syllabus_text=syllabus_text,
                canvas_config_id=config_id,
            )

            # Scrape assignments
            try:
                page.goto(
                    f"{canvas_url}/courses/{course_id}/assignments",
                    wait_until="networkidle", timeout=30_000,
                )
                assignments_html = page.content()
                assignments = parser.parse_assignments_page(assignments_html, course_id, course_name)

                for a in assignments:
                    self._db.upsert_task(
                        source="canvas",
                        external_id=a["external_id"],
                        title=a["title"],
                        course=a["course"],
                        deadline=a.get("due_date"),
                    )
                    total += 1
            except Exception as e:
                logger.warning("Failed to scrape assignments for %s: %s", course_name, e)

            # Scrape grades
            try:
                page.goto(
                    f"{canvas_url}/courses/{course_id}/grades",
                    wait_until="networkidle", timeout=30_000,
                )

                # Get the course's DB ID
                conn = self._db._get_conn()
                cursor = conn.execute("SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,))
                course_row = cursor.fetchone()
                db_course_id = course_row[0] if course_row else None

                if db_course_id:
                    # Extract grades via JS
                    grade_data = page.evaluate('''() => {
                        const rows = document.querySelectorAll('tr.student_assignment');
                        const grades = [];
                        rows.forEach(row => {
                            const titleEl = row.querySelector('th.title a, th.title span');
                            const scoreEl = row.querySelector('span.original_score, span.grade');
                            const possibleEl = row.querySelector('td.possible.points_possible');
                            if (!titleEl) return;
                            let score = scoreEl ? scoreEl.textContent.trim() : null;
                            if (score && (score.includes('Click to') || score.includes('Instructor has not'))) {
                                const num = score.match(/[\\d.]+/);
                                score = num ? num[0] : null;
                            }
                            grades.push({
                                name: titleEl.textContent.trim(),
                                score: score,
                                possible: possibleEl ? possibleEl.textContent.trim() : null,
                            });
                        });
                        const finalEl = document.querySelector('.final_grade .grade');
                        const finalGrade = finalEl ? finalEl.textContent.trim() : null;
                        return { grades, finalGrade };
                    }''')

                    # Store individual grades
                    for g in grade_data.get("grades", []):
                        if g["name"]:
                            status = "graded" if g["score"] else "ungraded"
                            self._db.upsert_grade(
                                course_id=db_course_id,
                                assignment_name=g["name"],
                                score=g["score"],
                                points_possible=g["possible"],
                                status=status,
                            )

                    # Store overall course grade
                    final = grade_data.get("finalGrade")
                    if final:
                        self._db.update_course_grade(db_course_id, final)
                        # Also update tasks with this grade
                        tasks = self._db.get_tasks(source="canvas")
                        for task in tasks:
                            if task["course"] == course_name:
                                self._db._get_conn().execute(
                                    "UPDATE tasks SET current_grade = ? WHERE id = ?",
                                    (final, task["id"]),
                                )
                        self._db._get_conn().commit()
            except Exception as e:
                logger.warning("Failed to scrape grades for %s: %s", course_name, e)

        # Scrape Canvas calendar page for events
        try:
            page.goto(f"{canvas_url}/calendar", wait_until="domcontentloaded", timeout=30_000)
            calendar_html = page.content()
            calendar_events = parser.parse_calendar_events(calendar_html)
            for evt in calendar_events:
                self._db.upsert_event(
                    account_id=None,
                    source="canvas",
                    external_id=f"canvas:cal:{evt['title'][:50]}:{evt.get('start_time', '')}",
                    title=evt["title"],
                    start_time=evt.get("start_time"),
                    event_type="class",
                )
                total += 1
        except Exception as e:
            logger.warning("Failed to scrape Canvas calendar: %s", e)

        # Update last sync
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._db.update_canvas_last_sync(config_id, now)

        page.close()
        return total

    def _is_session_expired(self, page, canvas_url: str) -> bool:
        """Check if the current page indicates a session expiry."""
        url = page.url
        if "/login" in url or "login" in url.split("/")[-1]:
            return True
        login_form = page.query_selector("#login_form")
        if login_form:
            return True
        return False


class _SessionExpiredError(Exception):
    pass
