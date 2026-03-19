import re


class CanvasParser:
    """Parse Canvas LMS HTML pages into structured data."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def parse_assignments_page(self, html: str, course_id: str, course_name: str) -> list[dict]:
        """Parse a course assignments page. Handles both relative and absolute URLs."""
        if not html:
            return []
        assignments = []

        # Find all assignment links — match href with /assignments/ID and class ig-title
        # in any attribute order
        link_pattern = re.compile(
            r'<a[^>]*href="[^"]*?/assignments/(\d+)"[^>]*class="ig-title"[^>]*>\s*(.*?)\s*</a>'
            r'|<a[^>]*class="ig-title"[^>]*href="[^"]*?/assignments/(\d+)"[^>]*>\s*(.*?)\s*</a>',
            re.DOTALL,
        )

        # Due dates — try tooltip pattern first (UT Austin), then date-text (other instances)
        date_pattern = re.compile(
            r'assignment-date-due.*?data-html-tooltip-title="([^"]+)"',
            re.DOTALL,
        )
        dates = date_pattern.findall(html)
        if not dates:
            dates = re.findall(r'<span class="date-text">([^<]+)</span>', html)

        for match in link_pattern.finditer(html):
            assignment_id = match.group(1) or match.group(3)
            title = match.group(2) or match.group(4)
            if not assignment_id:
                continue

            idx = len(assignments)
            assignments.append({
                "external_id": f"canvas:{course_id}:{assignment_id}",
                "title": title.strip(),
                "course": course_name,
                "due_date": dates[idx].strip() if idx < len(dates) else None,
            })

        return assignments

    def parse_grades_page(self, html: str, course_id: str) -> dict:
        """Parse a course grades page for the current grade."""
        if not html:
            return {"current_grade": None, "assignments": []}

        current_grade = None
        # Try multiple patterns used by different Canvas instances
        for pattern in [
            r'id="student-grades-final"[^>]*>.*?<span[^>]*class="grade"[^>]*>([^<]+)',
            r'class="final_grade"[^>]*>.*?<span[^>]*>([^<]+)',
            r'total-grade[^>]*>([^<]+)',
        ]:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                grade = match.group(1).strip()
                if grade:
                    current_grade = grade
                    break

        return {"current_grade": current_grade, "assignments": []}

    def parse_dashboard_todos(self, html: str) -> list[dict]:
        if not html:
            return []
        todos = []
        title_pattern = re.compile(r'todo-badge__info-holder__title">([^<]+)<')
        due_pattern = re.compile(r'todo-badge__info-holder__due">([^<]+)<')
        titles = title_pattern.findall(html)
        dues = due_pattern.findall(html)
        for i, title in enumerate(titles):
            todos.append({
                "title": title.strip(),
                "due_date": dues[i].strip() if i < len(dues) else None,
            })
        return todos

    def parse_calendar_events(self, html: str) -> list[dict]:
        if not html:
            return []
        events = []
        event_pattern = re.compile(
            r'class="fc-title">([^<]+)<.*?class="fc-time"[^>]*data-start="([^"]*)"',
            re.DOTALL,
        )
        for title, start_time in event_pattern.findall(html):
            events.append({"title": title.strip(), "start_time": start_time.strip()})
        return events

    def extract_course_list(self, html: str) -> list[dict]:
        """Extract courses — uses title attribute which contains course names."""
        if not html:
            return []
        courses = []
        seen = set()

        # Pattern: <a href="/courses/ID" title="Course Name"> (UT Austin pattern)
        pattern = re.compile(
            r'<a[^>]*href="[^"]*?/courses/(\d+)"[^>]*title="([^"]+)"',
            re.DOTALL,
        )
        for course_id, name in pattern.findall(html):
            if course_id not in seen:
                seen.add(course_id)
                courses.append({"id": course_id, "name": name.strip()})

        # Fallback: <a href="/courses/ID"><span class="name">Name</span>
        if not courses:
            pattern2 = re.compile(
                r'<a[^>]*href="[^"]*?/courses/(\d+)"[^>]*>.*?<span class="name[^"]*">([^<]+)</span>',
                re.DOTALL,
            )
            for course_id, name in pattern2.findall(html):
                if course_id not in seen:
                    seen.add(course_id)
                    courses.append({"id": course_id, "name": name.strip()})

        return courses
