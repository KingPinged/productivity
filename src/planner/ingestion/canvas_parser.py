import re


class CanvasParser:
    """Parse Canvas LMS HTML pages into structured data."""

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")

    def parse_assignments_page(self, html: str, course_id: str, course_name: str) -> list[dict]:
        if not html:
            return []
        assignments = []
        link_pattern = re.compile(
            r'<a[^>]*class="ig-title"[^>]*href="[^"]*?/assignments/(\d+)"[^>]*>([^<]+)</a>',
            re.DOTALL,
        )
        date_pattern = re.compile(r'<span class="date-text">([^<]+)</span>')
        points_pattern = re.compile(r'<span class="points_possible">([^<]+)</span>')

        links = link_pattern.findall(html)
        dates = date_pattern.findall(html)
        points = points_pattern.findall(html)

        for i, (assignment_id, title) in enumerate(links):
            assignment = {
                "external_id": f"canvas:{course_id}:{assignment_id}",
                "title": title.strip(),
                "course": course_name,
                "due_date": dates[i].strip() if i < len(dates) else None,
                "points": points[i].strip() if i < len(points) else None,
            }
            assignments.append(assignment)
        return assignments

    def parse_grades_page(self, html: str, course_id: str) -> dict:
        if not html:
            return {"current_grade": None, "assignments": []}
        grade_match = re.search(
            r'<div[^>]*id="student-grades-final"[^>]*>.*?<span class="grade">([^<]+)</span>',
            html, re.DOTALL,
        )
        current_grade = grade_match.group(1).strip() if grade_match else None
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
        if not html:
            return []
        courses = []
        pattern = re.compile(
            r'<a[^>]*href="/courses/(\d+)"[^>]*>.*?<span class="name[^"]*">([^<]+)</span>',
            re.DOTALL,
        )
        for course_id, name in pattern.findall(html):
            courses.append({"id": course_id, "name": name.strip()})
        return courses
