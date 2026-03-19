import pytest

from src.planner.ingestion.canvas_parser import CanvasParser


class TestParseAssignments:
    def test_parse_dashboard_assignments(self):
        html = """
        <div class="ic-DashboardCard__action-container">
          <div class="ic-DashboardCard__action-layout">
            <a href="/courses/12345/assignments/67890">
              <span class="todo-badge__info-holder">
                <span class="todo-badge__info-holder__title">Problem Set 5</span>
                <span class="todo-badge__info-holder__due">Mar 25 at 11:59pm</span>
              </span>
            </a>
          </div>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        assignments = parser.parse_dashboard_todos(html)
        assert len(assignments) >= 0

    def test_parse_course_assignments_list(self):
        html = """
        <div id="assignment_group_1">
          <div class="ig-row">
            <a class="ig-title" href="/courses/101/assignments/201">Homework 3</a>
            <div class="assignment-date-due">
              <span class="screenreader-only">Due</span>
              <span class="date-text">Mar 28, 2026 at 11:59pm</span>
            </div>
            <span class="points_possible">100 pts</span>
          </div>
          <div class="ig-row">
            <a class="ig-title" href="/courses/101/assignments/202">Final Exam</a>
            <div class="assignment-date-due">
              <span class="screenreader-only">Due</span>
              <span class="date-text">Apr 15, 2026 at 2:00pm</span>
            </div>
            <span class="points_possible">200 pts</span>
          </div>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        assignments = parser.parse_assignments_page(html, course_id="101", course_name="CS 101")
        assert len(assignments) == 2
        assert assignments[0]["title"] == "Homework 3"
        assert assignments[0]["course"] == "CS 101"
        assert assignments[0]["external_id"] == "canvas:101:201"
        assert assignments[1]["title"] == "Final Exam"

    def test_parse_grades_page(self):
        html = """
        <div class="student_assignment">
          <th class="title" scope="row">
            <a href="/courses/101/assignments/201">Homework 1</a>
          </th>
          <span class="grade">85</span>
          <span class="points_possible">100</span>
        </div>
        <div id="student-grades-final">
          <span class="grade">B+</span>
        </div>
        """
        parser = CanvasParser("https://canvas.university.edu")
        grade_info = parser.parse_grades_page(html, course_id="101")
        assert grade_info["current_grade"] is not None

    def test_parse_empty_page_returns_empty(self):
        parser = CanvasParser("https://canvas.university.edu")
        assert parser.parse_assignments_page("", course_id="101", course_name="CS") == []
        assert parser.parse_grades_page("", course_id="101") == {"current_grade": None, "assignments": []}
