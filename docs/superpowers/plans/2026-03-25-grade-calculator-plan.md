# Grade Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weighted grade calculator with what-if editing to the courses tab in the React + FastAPI web app.

**Architecture:** Extend the existing SQLite schema with `grade_categories` and `grade_scales` tables. Port canvasGet's regex syllabus parsing to Python. Add FastAPI endpoints for grade computation. Build a React component with client-side grade calculation and inline score editing.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), SQLite (database), regex (syllabus parsing)

**Target branch:** `feat/ai-scheduling-assistant-phase1`

---

### Task 1: Schema — Add grade_categories, grade_scales tables and grades.category column

**Files:**
- Modify: `src/planner/db.py`

- [ ] **Step 1: Add new tables to SCHEMA_SQL**

In `src/planner/db.py`, add these table definitions to the end of the `SCHEMA_SQL` string (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS grade_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    name TEXT NOT NULL,
    weight REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'auto',
    UNIQUE(course_id, name)
);

CREATE TABLE IF NOT EXISTS grade_scales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER REFERENCES courses(id),
    letter TEXT NOT NULL,
    min_percent REAL NOT NULL,
    max_percent REAL,
    UNIQUE(course_id, letter)
);
```

- [ ] **Step 2: Add migration for grades.category column**

In the `initialize()` method of `PlannerDB`, add this migration after the existing `syllabus_file` migration:

```python
# Migration: add category to grades if missing
try:
    conn.execute("ALTER TABLE grades ADD COLUMN category TEXT")
    conn.commit()
except Exception:
    pass  # Column already exists
```

- [ ] **Step 3: Add CRUD methods for grade_categories**

Add these methods to `PlannerDB`:

```python
def upsert_grade_category(self, course_id: int, name: str, weight: float, source: str = "auto") -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT id FROM grade_categories WHERE course_id = ? AND name = ?",
        (course_id, name),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            "UPDATE grade_categories SET weight=?, source=? WHERE id=?",
            (weight, source, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        "INSERT INTO grade_categories (course_id, name, weight, source) VALUES (?, ?, ?, ?)",
        (course_id, name, weight, source),
    )
    conn.commit()
    return cursor.lastrowid

def get_grade_categories(self, course_id: int) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM grade_categories WHERE course_id = ? ORDER BY name",
        (course_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def set_grade_categories(self, course_id: int, categories: list[dict], source: str = "manual") -> None:
    conn = self._get_conn()
    conn.execute("DELETE FROM grade_categories WHERE course_id = ?", (course_id,))
    for cat in categories:
        conn.execute(
            "INSERT INTO grade_categories (course_id, name, weight, source) VALUES (?, ?, ?, ?)",
            (course_id, cat["name"], cat["weight"], source),
        )
    conn.commit()

def has_grade_categories(self, course_id: int) -> bool:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM grade_categories WHERE course_id = ?", (course_id,),
    )
    return cursor.fetchone()[0] > 0
```

- [ ] **Step 4: Add CRUD methods for grade_scales**

Add these methods to `PlannerDB`:

```python
def upsert_grade_scale(self, course_id: int, letter: str, min_percent: float, max_percent: float | None = None) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT id FROM grade_scales WHERE course_id = ? AND letter = ?",
        (course_id, letter),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            "UPDATE grade_scales SET min_percent=?, max_percent=? WHERE id=?",
            (min_percent, max_percent, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        "INSERT INTO grade_scales (course_id, letter, min_percent, max_percent) VALUES (?, ?, ?, ?)",
        (course_id, letter, min_percent, max_percent),
    )
    conn.commit()
    return cursor.lastrowid

def get_grade_scale(self, course_id: int) -> list[dict]:
    conn = self._get_conn()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT * FROM grade_scales WHERE course_id = ? ORDER BY min_percent DESC",
        (course_id,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.row_factory = None
    return rows

def set_grade_scale(self, course_id: int, scale: list[dict]) -> None:
    conn = self._get_conn()
    conn.execute("DELETE FROM grade_scales WHERE course_id = ?", (course_id,))
    for entry in scale:
        conn.execute(
            "INSERT INTO grade_scales (course_id, letter, min_percent, max_percent) VALUES (?, ?, ?, ?)",
            (course_id, entry["letter"], entry["min_percent"], entry.get("max_percent")),
        )
    conn.commit()
```

- [ ] **Step 5: Add method to update grade category assignment**

Add to `PlannerDB`:

```python
def update_grade_category(self, grade_id: int, category: str | None) -> None:
    conn = self._get_conn()
    conn.execute("UPDATE grades SET category = ? WHERE id = ?", (category, grade_id))
    conn.commit()
```

- [ ] **Step 6: Update upsert_grade to accept category**

Modify the existing `upsert_grade` method signature and body:

```python
def upsert_grade(self, course_id: int, assignment_name: str, score: str | None = None,
                 points_possible: str | None = None, status: str = "graded",
                 category: str | None = None) -> int:
    conn = self._get_conn()
    cursor = conn.execute(
        "SELECT id FROM grades WHERE course_id = ? AND assignment_name = ?",
        (course_id, assignment_name),
    )
    row = cursor.fetchone()
    if row:
        conn.execute(
            "UPDATE grades SET score=?, points_possible=?, status=?, category=? WHERE id=?",
            (score, points_possible, status, category, row[0]),
        )
        conn.commit()
        return row[0]
    cursor = conn.execute(
        "INSERT INTO grades (course_id, assignment_name, score, points_possible, status, category) VALUES (?, ?, ?, ?, ?, ?)",
        (course_id, assignment_name, score, points_possible, status, category),
    )
    conn.commit()
    return cursor.lastrowid
```

- [ ] **Step 7: Commit**

```bash
git add src/planner/db.py
git commit -m "feat: add grade_categories and grade_scales tables with CRUD methods"
```

---

### Task 2: Syllabus Parser — Port canvasGet regex extraction to Python

**Files:**
- Create: `src/planner/ingestion/syllabus_parser.py`

- [ ] **Step 1: Create syllabus_parser.py with extract_grade_weights**

Create `src/planner/ingestion/syllabus_parser.py`:

```python
"""
Parse syllabus text to extract grade weights, grade scales, and expected assignments.

Ported from canvasGet's TypeScript regex extraction (src/scraper.ts).
"""

import re


def extract_grade_weights(text: str) -> list[dict]:
    """Extract category weight percentages from syllabus text.

    Matches patterns like "Homework 30%", "Exams: 40%", "30% Homework".
    Returns [{"category": str, "weight": str}].
    """
    weights: list[dict] = []
    seen_lower: set[str] = set()

    category_words = (
        r"(?:homework|assignments?|quizzes?|quiz|exams?|midterms?|mid-?term|finals?"
        r"|final\s+exam|participation|attendance|labs?|laboratory|projects?|papers?"
        r"|essays?|discussion|presentations?|classwork|class\s*work|reading"
        r"|problem\s+sets?|tests?)"
    )

    # Category first: "Homework 30%", "Exams: 40%"
    pattern = re.compile(
        rf"({category_words}(?:\s+\w+)?)\s*[:=]?\s*(\d{{1,3}}(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    )
    for m in pattern.finditer(text):
        category = m.group(1).strip()
        num = float(m.group(2))
        if 0 < num <= 100:
            weights.append({"category": category, "weight": f"{m.group(2)}%"})
            seen_lower.add(category.lower())

    # Reversed: "30% Homework"
    reversed_pattern = re.compile(
        rf"(\d{{1,3}}(?:\.\d+)?)\s*%\s*[:=\-]?\s*({category_words}(?:\s+\w+)?)",
        re.IGNORECASE,
    )
    for m in reversed_pattern.finditer(text):
        category = m.group(2).strip()
        num = float(m.group(1))
        if 0 < num <= 100 and category.lower() not in seen_lower:
            weights.append({"category": category, "weight": f"{m.group(1)}%"})
            seen_lower.add(category.lower())

    return weights


def extract_grade_scale(text: str) -> list[dict]:
    """Extract letter grade thresholds from syllabus text.

    Matches patterns like "A: 90-100", "A = 93-100", "A >= 90", "90-100 A".
    Returns sorted [{"letter": str, "min_percent": float, "max_percent": float | None}].
    """
    scale: list[dict] = []

    # Letter-first range: "A: 90-100", "A = 90 - 100", "A 90%-100%"
    letter_first = re.compile(
        r"\b([A-DF][+-]?)\s*[:=\s]+\s*(\d{1,3}(?:\.\d+)?)\s*%?\s*[-\u2013\u2014to]+\s*(\d{1,3}(?:\.\d+)?)\s*%?",
        re.IGNORECASE,
    )
    for m in letter_first.finditer(text):
        letter = m.group(1).upper()
        num1 = float(m.group(2))
        num2 = float(m.group(3))
        if 0 <= num1 <= 100 and 0 <= num2 <= 100:
            scale.append({"letter": letter, "min_percent": min(num1, num2), "max_percent": max(num1, num2)})

    # Number-first range: "90-100 = A", "90-100: A"
    if not scale:
        num_first = re.compile(
            r"(\d{1,3}(?:\.\d+)?)\s*%?\s*[-\u2013\u2014to]+\s*(\d{1,3}(?:\.\d+)?)\s*%?\s*[:=\s]+\s*([A-DF][+-]?)\b",
            re.IGNORECASE,
        )
        for m in num_first.finditer(text):
            num1 = float(m.group(1))
            num2 = float(m.group(2))
            letter = m.group(3).upper()
            if 0 <= num1 <= 100 and 0 <= num2 <= 100:
                scale.append({"letter": letter, "min_percent": min(num1, num2), "max_percent": max(num1, num2)})

    # Simple "A >= 90" or "A: 90" pattern
    if not scale:
        simple = re.compile(
            r"\b([A-DF][+-]?)\s*[:=\s]+\s*(?:>=?\s*)?(\d{1,3}(?:\.\d+)?)\s*%?"
            r"(?:\s*(?:and above|or above|or higher|\+|above))?",
            re.IGNORECASE,
        )
        found: list[dict] = []
        seen: set[str] = set()
        for m in simple.finditer(text):
            letter = m.group(1).upper()
            min_val = float(m.group(2))
            if 0 <= min_val <= 100 and re.match(r"^[A-DF][+-]?$", letter) and letter not in seen:
                seen.add(letter)
                found.append({"letter": letter, "min": min_val})
        found.sort(key=lambda x: x["min"], reverse=True)
        for i, entry in enumerate(found):
            scale.append({
                "letter": entry["letter"],
                "min_percent": entry["min"],
                "max_percent": 100.0 if i == 0 else found[i - 1]["min"] - 0.01,
            })

    # Deduplicate by letter, keep first occurrence
    seen_letters: dict[str, dict] = {}
    for s in scale:
        if s["letter"] not in seen_letters:
            seen_letters[s["letter"]] = s
    return sorted(seen_letters.values(), key=lambda x: x["min_percent"], reverse=True)


def map_assignment_to_category(
    assignment_name: str,
    category_names: list[str],
) -> str | None:
    """Fuzzy-match an assignment name to the best matching category.

    Returns the category name or None if no match.
    """
    name_lower = assignment_name.lower()

    # Direct keyword mapping
    keyword_map = {
        "homework": ["homework", "hw", "assignment"],
        "quiz": ["quiz", "quizzes"],
        "exam": ["exam", "midterm", "mid-term", "test", "final"],
        "lab": ["lab", "laboratory"],
        "project": ["project"],
        "paper": ["paper", "essay"],
        "participation": ["participation", "attendance"],
        "discussion": ["discussion", "forum", "post"],
        "presentation": ["presentation"],
    }

    # For each category, check if the assignment name contains keywords
    best_match: str | None = None
    best_score = 0

    for cat_name in category_names:
        cat_lower = cat_name.lower()
        score = 0

        # Exact substring match of category name in assignment
        if cat_lower in name_lower:
            score = 10

        # Check keyword overlap
        for base_word, keywords in keyword_map.items():
            cat_has = any(kw in cat_lower for kw in keywords) or base_word in cat_lower
            name_has = any(kw in name_lower for kw in keywords) or base_word in name_lower
            if cat_has and name_has:
                score = max(score, 5)

        if score > best_score:
            best_score = score
            best_match = cat_name

    return best_match if best_score >= 5 else None


def parse_syllabus_for_course(syllabus_text: str) -> dict:
    """Parse syllabus text and return structured grade info.

    Returns {"grade_weights": [...], "grade_scale": [...]}.
    """
    return {
        "grade_weights": extract_grade_weights(syllabus_text),
        "grade_scale": extract_grade_scale(syllabus_text),
    }
```

- [ ] **Step 2: Commit**

```bash
git add src/planner/ingestion/syllabus_parser.py
git commit -m "feat: add syllabus parser with grade weight and scale extraction"
```

---

### Task 3: Grade Calculator API — Add endpoints for grade computation and management

**Files:**
- Create: `src/planner/api/grade_calculator.py`
- Modify: `src/planner/server.py`

- [ ] **Step 1: Create grade_calculator.py API router**

Create `src/planner/api/grade_calculator.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from src.planner.db import PlannerDB
from src.planner.ingestion.syllabus_parser import (
    parse_syllabus_for_course,
    map_assignment_to_category,
)

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


@router.put("/courses/{course_id}/grade-scale")
def update_grade_scale(course_id: int, body: ScaleBody, db: PlannerDB = Depends(get_db)):
    db.set_grade_scale(
        course_id,
        [{"letter": s.letter, "min_percent": s.min_percent, "max_percent": s.max_percent} for s in body.scale],
    )
    return {"ok": True}


@router.post("/courses/{course_id}/reparse-syllabus")
def reparse_syllabus(course_id: int, db: PlannerDB = Depends(get_db)):
    course = db.get_course(course_id)
    if not course:
        return {"error": "Course not found"}

    syllabus_text = course.get("syllabus_text") or ""
    if not syllabus_text.strip():
        return {"error": "No syllabus text available", "parsed": False}

    parsed = parse_syllabus_for_course(syllabus_text)

    # Delete existing auto-parsed entries, keep manual
    conn = db._get_conn()
    conn.execute(
        "DELETE FROM grade_categories WHERE course_id = ? AND source = 'auto'",
        (course_id,),
    )
    conn.execute("DELETE FROM grade_scales WHERE course_id = ?", (course_id,))
    conn.commit()

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
```

- [ ] **Step 2: Register the router in server.py**

In `src/planner/server.py`, add the import near the other API imports:

```python
from src.planner.api import grade_calculator as grade_calc_module
```

Then add these lines after the courses router registration block (after `app.include_router(courses_module.public_router)`):

```python
# Grade calculator routes
app.dependency_overrides[grade_calc_module.get_db] = get_db
for route in grade_calc_module.router.routes:
    route.dependencies = [require_token]
app.include_router(grade_calc_module.router)
```

- [ ] **Step 3: Commit**

```bash
git add src/planner/api/grade_calculator.py src/planner/server.py
git commit -m "feat: add grade calculator API with weighted computation and simulation"
```

---

### Task 4: Canvas Sync Integration — Auto-parse syllabus and store assignment categories on sync

**Files:**
- Modify: `src/planner/ingestion/canvas_requests.py`

- [ ] **Step 1: Add import for syllabus_parser**

At the top of `src/planner/ingestion/canvas_requests.py`, add:

```python
from src.planner.ingestion.syllabus_parser import parse_syllabus_for_course, map_assignment_to_category
```

- [ ] **Step 2: Add grade scraping with categories to sync_config**

In the `sync_config` method, find the section that fetches grades via enrollments API (the `# Get grades via API` block). Replace it with this expanded version that also fetches per-assignment grades with categories:

```python
            # Get per-assignment grades via submissions API
            try:
                # Get assignment groups for category mapping
                groups = self._api_get(
                    session, f"{api_url}/courses/{course_id}/assignment_groups",
                    {"include[]": "assignments", "per_page": "50"}
                )
                group_map = {}
                if groups:
                    for grp in groups:
                        group_map[grp["id"]] = grp.get("name", "Uncategorized")

                submissions = self._api_get(
                    session,
                    f"{api_url}/courses/{course_id}/students/submissions",
                    {"student_ids[]": "self", "include[]": "assignment", "per_page": "100"}
                )
                if submissions:
                    db_course = None
                    cursor = conn = None
                    conn = self._db._get_conn()
                    cursor = conn.execute(
                        "SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,)
                    )
                    row = cursor.fetchone()
                    db_course_id = row[0] if row else None

                    if db_course_id:
                        for sub in submissions:
                            assignment = sub.get("assignment")
                            if not assignment or assignment.get("published") is False:
                                continue

                            a_name = assignment.get("name", "Untitled")
                            points_possible = assignment.get("points_possible")
                            group_id = assignment.get("assignment_group_id")
                            cat_name = group_map.get(group_id, "Uncategorized") if group_id else None

                            score = None
                            if (sub.get("score") is not None
                                    and sub.get("workflow_state") == "graded"
                                    and sub.get("grade") is not None):
                                score = str(sub["score"])

                            self._db.upsert_grade(
                                course_id=db_course_id,
                                assignment_name=a_name,
                                score=score,
                                points_possible=str(points_possible) if points_possible else None,
                                status="graded" if score else "pending",
                                category=cat_name,
                            )
            except Exception as e:
                logger.warning("Failed submission grades for %s: %s", course_name, e)

            # Get overall grade from enrollments
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
                logger.warning("Failed enrollment grades for %s: %s", course_name, e)
```

- [ ] **Step 3: Add syllabus auto-parsing after course upsert**

In `sync_config`, after the `# Save course` block (`self._db.upsert_course(...)` call), add:

```python
            # Auto-parse syllabus for grade weights if we have text
            if syllabus_text and syllabus_text.strip():
                conn_inner = self._db._get_conn()
                cursor_inner = conn_inner.execute(
                    "SELECT id FROM courses WHERE canvas_course_id = ?", (course_id,)
                )
                row_inner = cursor_inner.fetchone()
                if row_inner:
                    db_cid = row_inner[0]
                    if not self._db.has_grade_categories(db_cid):
                        parsed = parse_syllabus_for_course(syllabus_text)
                        for w in parsed["grade_weights"]:
                            weight_num = float(w["weight"].replace("%", ""))
                            self._db.upsert_grade_category(db_cid, w["category"], weight_num, source="auto")
                        for s in parsed["grade_scale"]:
                            self._db.upsert_grade_scale(db_cid, s["letter"], s["min_percent"], s.get("max_percent"))
```

- [ ] **Step 4: Commit**

```bash
git add src/planner/ingestion/canvas_requests.py
git commit -m "feat: scrape per-assignment grades with categories and auto-parse syllabus on sync"
```

---

### Task 5: Frontend Types — Add grade calculator type definitions

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add grade calculator types**

Append to `frontend/src/types/index.ts`:

```typescript
export interface GradeCategory {
  name: string
  weight: number
  earned: number
  possible: number
  score: number | null
  assignments: GradeAssignment[]
}

export interface GradeAssignment {
  id: number | null
  name: string
  score: string | null
  points_possible: string | null
  category: string
  hypothetical?: boolean
}

export interface GradeScaleEntry {
  letter: string
  minPercent: number
  maxPercent: number | null
}

export interface GradeCalculatorData {
  categories: GradeCategory[]
  weightedGrade: number | null
  letterGrade: string | null
  gradeScale: GradeScaleEntry[]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add grade calculator TypeScript type definitions"
```

---

### Task 6: Frontend Hook — useGradeCalculator with client-side computation

**Files:**
- Create: `frontend/src/hooks/useGradeCalculator.ts`

- [ ] **Step 1: Create the hook**

Create `frontend/src/hooks/useGradeCalculator.ts`:

```typescript
import { useState, useEffect, useCallback, useMemo } from 'react'
import { apiFetch } from '../api/client'
import type { GradeCalculatorData, GradeCategory, GradeScaleEntry } from '../types'

interface Override {
  gradeId: number | null
  category: string
  name: string
  score: number
  pointsPossible: number
}

export function useGradeCalculator(courseId: number | null) {
  const [data, setData] = useState<GradeCalculatorData | null>(null)
  const [loading, setLoading] = useState(false)
  const [overrides, setOverrides] = useState<Map<string, Override>>(new Map())

  const load = useCallback(async () => {
    if (!courseId) return
    setLoading(true)
    try {
      const result = await apiFetch<GradeCalculatorData>(`/api/courses/${courseId}/grade-calculator`)
      setData(result)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    load()
    setOverrides(new Map())
  }, [load])

  const setOverride = useCallback((key: string, override: Override) => {
    setOverrides(prev => {
      const next = new Map(prev)
      next.set(key, override)
      return next
    })
  }, [])

  const removeOverride = useCallback((key: string) => {
    setOverrides(prev => {
      const next = new Map(prev)
      next.delete(key)
      return next
    })
  }, [])

  const resetOverrides = useCallback(() => {
    setOverrides(new Map())
  }, [])

  // Client-side grade computation with overrides applied
  const computed = useMemo(() => {
    if (!data) return null
    return computeWithOverrides(data, overrides)
  }, [data, overrides])

  const saveCategories = useCallback(async (categories: Array<{ name: string; weight: number }>) => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/grade-categories`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ categories }),
    })
    await load()
  }, [courseId, load])

  const saveScale = useCallback(async (scale: Array<{ letter: string; min_percent: number; max_percent: number | null }>) => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/grade-scale`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scale }),
    })
    await load()
  }, [courseId, load])

  const reparseSyllabus = useCallback(async () => {
    if (!courseId) return
    await apiFetch(`/api/courses/${courseId}/reparse-syllabus`, { method: 'POST' })
    await load()
  }, [courseId, load])

  return {
    data: computed,
    rawData: data,
    loading,
    overrides,
    setOverride,
    removeOverride,
    resetOverrides,
    saveCategories,
    saveScale,
    reparseSyllabus,
    reload: load,
  }
}

function computeWithOverrides(
  data: GradeCalculatorData,
  overrides: Map<string, Override>,
): GradeCalculatorData {
  if (overrides.size === 0) return data

  const categories: GradeCategory[] = data.categories.map(cat => {
    let earned = 0
    let possible = 0
    const assignments = cat.assignments.map(a => {
      const key = a.id != null ? `existing-${a.id}` : `hyp-${a.name}`
      const ov = overrides.get(key)
      const score = ov ? String(ov.score) : a.score
      const pp = ov ? String(ov.pointsPossible) : a.points_possible
      const scoreNum = score != null ? parseFloat(score) : null
      const ppNum = pp != null ? parseFloat(pp) : null

      if (scoreNum != null && !isNaN(scoreNum) && ppNum != null && !isNaN(ppNum) && ppNum > 0) {
        earned += scoreNum
        possible += ppNum
      }

      return { ...a, score, points_possible: pp }
    })

    // Add new hypothetical overrides for this category
    for (const [key, ov] of overrides) {
      if (key.startsWith('new-') && ov.category === cat.name) {
        assignments.push({
          id: null,
          name: ov.name || 'Hypothetical',
          score: String(ov.score),
          points_possible: String(ov.pointsPossible),
          category: cat.name,
          hypothetical: true,
        })
        earned += ov.score
        possible += ov.pointsPossible
      }
    }

    return {
      ...cat,
      earned,
      possible,
      score: possible > 0 ? Math.round(earned / possible * 10000) / 100 : null,
      assignments,
    }
  })

  // Weighted grade
  let activeWeightSum = 0
  let weightedSum = 0
  for (const cat of categories) {
    if (cat.weight > 0 && cat.score != null) {
      weightedSum += cat.score * cat.weight / 100
      activeWeightSum += cat.weight
    }
  }

  let weightedGrade: number | null = null
  if (activeWeightSum > 0) {
    weightedGrade = Math.round(weightedSum / activeWeightSum * 10000) / 100
  } else {
    const totalEarned = categories.reduce((s, c) => s + c.earned, 0)
    const totalPossible = categories.reduce((s, c) => s + c.possible, 0)
    weightedGrade = totalPossible > 0 ? Math.round(totalEarned / totalPossible * 10000) / 100 : null
  }

  // Letter grade
  let letterGrade: string | null = null
  if (weightedGrade != null && data.gradeScale.length > 0) {
    const sorted = [...data.gradeScale].sort((a, b) => b.minPercent - a.minPercent)
    for (const entry of sorted) {
      if (weightedGrade >= entry.minPercent) {
        letterGrade = entry.letter
        break
      }
    }
  }

  return { categories, weightedGrade, letterGrade, gradeScale: data.gradeScale }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/useGradeCalculator.ts
git commit -m "feat: add useGradeCalculator hook with client-side weighted computation"
```

---

### Task 7: Frontend Component — GradeCalculator with inline editing

**Files:**
- Create: `frontend/src/components/GradeCalculator.tsx`

- [ ] **Step 1: Create GradeCalculator component**

Create `frontend/src/components/GradeCalculator.tsx`:

```tsx
import { useState, useRef, useEffect } from 'react'
import { useGradeCalculator } from '../hooks/useGradeCalculator'
import type { GradeCategory, GradeAssignment } from '../types'

export default function GradeCalculator({ courseId }: { courseId: number }) {
  const {
    data, loading, overrides,
    setOverride, removeOverride, resetOverrides,
    saveCategories, saveScale, reparseSyllabus,
  } = useGradeCalculator(courseId)
  const [editingWeights, setEditingWeights] = useState(false)
  const hasOverrides = overrides.size > 0

  if (loading) return <div className="text-muted text-sm">Loading grades...</div>
  if (!data) return <div className="text-muted text-sm">No grade data available.</div>

  const hasCategories = data.categories.some(c => c.weight > 0)

  return (
    <div className="mt-6">
      {/* Overall Grade Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="font-display font-semibold text-sm text-secondary uppercase tracking-wider">Grade Calculator</h3>
          <button
            onClick={() => setEditingWeights(!editingWeights)}
            className="text-muted hover:text-secondary text-xs"
            title="Edit weights & scale"
          >
            {'\u2699'}
          </button>
          {hasOverrides && (
            <button
              onClick={resetOverrides}
              className="text-xs text-accent hover:text-accent-hover font-medium"
            >
              Reset what-if
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data.letterGrade && (
            <span className="text-sm font-semibold text-white bg-accent px-2.5 py-0.5 rounded-full">
              {data.letterGrade}
            </span>
          )}
          {data.weightedGrade != null && (
            <span className="text-2xl font-display font-bold text-primary">
              {data.weightedGrade}%
            </span>
          )}
        </div>
      </div>

      {/* Weights Editor */}
      {editingWeights && (
        <WeightsEditor
          categories={data.categories}
          gradeScale={data.gradeScale}
          onSaveCategories={saveCategories}
          onSaveScale={saveScale}
          onReparse={reparseSyllabus}
          onClose={() => setEditingWeights(false)}
        />
      )}

      {/* No categories hint */}
      {!hasCategories && (
        <div className="p-3 bg-cream rounded-lg mb-4 text-sm text-secondary">
          No category weights found. Click the gear icon to add them manually or re-parse the syllabus.
        </div>
      )}

      {/* Category Sections */}
      {data.categories.map(cat => (
        <CategorySection
          key={cat.name}
          category={cat}
          overrides={overrides}
          onSetOverride={setOverride}
          onRemoveOverride={removeOverride}
        />
      ))}
    </div>
  )
}

function CategorySection({
  category, overrides, onSetOverride, onRemoveOverride,
}: {
  category: GradeCategory
  overrides: Map<string, any>
  onSetOverride: (key: string, ov: any) => void
  onRemoveOverride: (key: string) => void
}) {
  const [expanded, setExpanded] = useState(true)
  const [addingNew, setAddingNew] = useState(false)

  return (
    <div className="mb-3 bg-sand rounded-xl overflow-hidden">
      {/* Category Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-border/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className={`text-muted text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>{'\u25B6'}</span>
          <span className="font-medium text-sm text-primary">{category.name}</span>
          {category.weight > 0 && (
            <span className="text-[10px] font-medium text-accent bg-accent-light px-1.5 py-0.5 rounded-full">
              {category.weight}%
            </span>
          )}
        </div>
        <span className="text-sm font-medium text-primary">
          {category.score != null ? `${category.score}%` : '-'}
        </span>
      </button>

      {/* Assignments */}
      {expanded && (
        <div className="border-t border-border/50 px-3 pb-2">
          {category.assignments.map((a, i) => (
            <AssignmentRow
              key={a.id ?? `hyp-${i}`}
              assignment={a}
              overrides={overrides}
              onSetOverride={onSetOverride}
              onRemoveOverride={onRemoveOverride}
            />
          ))}
          {/* Add hypothetical */}
          {addingNew ? (
            <NewAssignmentRow
              category={category.name}
              onAdd={(ov) => {
                const key = `new-${Date.now()}`
                onSetOverride(key, ov)
                setAddingNew(false)
              }}
              onCancel={() => setAddingNew(false)}
            />
          ) : (
            <button
              onClick={() => setAddingNew(true)}
              className="text-xs text-accent hover:text-accent-hover font-medium py-1.5"
            >
              + Add assignment
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function AssignmentRow({
  assignment, overrides, onSetOverride, onRemoveOverride,
}: {
  assignment: GradeAssignment
  overrides: Map<string, any>
  onSetOverride: (key: string, ov: any) => void
  onRemoveOverride: (key: string) => void
}) {
  const key = assignment.id != null ? `existing-${assignment.id}` : `hyp-${assignment.name}`
  const hasOverride = overrides.has(key)
  const [editing, setEditing] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [editing])

  const scoreDisplay = assignment.score ?? '-'
  const ppDisplay = assignment.points_possible ?? '?'

  const handleSubmit = (value: string) => {
    const num = parseFloat(value)
    if (!isNaN(num)) {
      onSetOverride(key, {
        gradeId: assignment.id,
        category: assignment.category,
        name: assignment.name,
        score: num,
        pointsPossible: parseFloat(assignment.points_possible || '100'),
      })
    }
    setEditing(false)
  }

  return (
    <div className={`flex items-center justify-between py-1.5 border-b border-border/30 last:border-0 ${
      assignment.hypothetical ? 'bg-accent-light/30' : ''
    } ${hasOverride ? 'bg-amber-50' : ''}`}>
      <span className="text-sm text-primary truncate flex-1">{assignment.name}</span>
      <div className="flex items-center gap-1 ml-2">
        {editing ? (
          <input
            ref={inputRef}
            type="number"
            defaultValue={assignment.score ?? ''}
            className="w-16 text-sm text-right border border-accent rounded px-1 py-0.5"
            onBlur={(e) => handleSubmit(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmit((e.target as HTMLInputElement).value)
              if (e.key === 'Escape') setEditing(false)
            }}
          />
        ) : (
          <button
            onClick={() => setEditing(true)}
            className={`text-sm font-medium text-right min-w-[3rem] ${
              assignment.score ? 'text-primary' : 'text-muted border-b border-dashed border-muted'
            } ${hasOverride ? 'text-amber-700 font-semibold' : ''} hover:text-accent cursor-pointer`}
          >
            {scoreDisplay}
          </button>
        )}
        <span className="text-sm text-muted">/ {ppDisplay}</span>
        {hasOverride && (
          <button
            onClick={() => onRemoveOverride(key)}
            className="text-xs text-muted hover:text-red-500 ml-1"
            title="Remove override"
          >
            {'\u2715'}
          </button>
        )}
      </div>
    </div>
  )
}

function NewAssignmentRow({
  category, onAdd, onCancel,
}: {
  category: string
  onAdd: (ov: any) => void
  onCancel: () => void
}) {
  const [score, setScore] = useState('')
  const [total, setTotal] = useState('100')
  const scoreRef = useRef<HTMLInputElement>(null)

  useEffect(() => { scoreRef.current?.focus() }, [])

  const handleAdd = () => {
    const s = parseFloat(score)
    const t = parseFloat(total)
    if (!isNaN(s) && !isNaN(t) && t > 0) {
      onAdd({
        gradeId: null,
        category,
        name: `What-if ${category}`,
        score: s,
        pointsPossible: t,
      })
    }
  }

  return (
    <div className="flex items-center gap-2 py-1.5">
      <input
        ref={scoreRef}
        type="number"
        placeholder="Score"
        value={score}
        onChange={e => setScore(e.target.value)}
        className="w-16 text-sm border border-border rounded px-1.5 py-0.5"
        onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') onCancel() }}
      />
      <span className="text-sm text-muted">/</span>
      <input
        type="number"
        placeholder="Total"
        value={total}
        onChange={e => setTotal(e.target.value)}
        className="w-16 text-sm border border-border rounded px-1.5 py-0.5"
        onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') onCancel() }}
      />
      <button onClick={handleAdd} className="text-xs text-accent font-medium">Add</button>
      <button onClick={onCancel} className="text-xs text-muted">Cancel</button>
    </div>
  )
}

function WeightsEditor({
  categories, gradeScale, onSaveCategories, onSaveScale, onReparse, onClose,
}: {
  categories: GradeCategory[]
  gradeScale: Array<{ letter: string; minPercent: number; maxPercent: number | null }>
  onSaveCategories: (cats: Array<{ name: string; weight: number }>) => Promise<void>
  onSaveScale: (scale: Array<{ letter: string; min_percent: number; max_percent: number | null }>) => Promise<void>
  onReparse: () => Promise<void>
  onClose: () => void
}) {
  const [cats, setCats] = useState(
    categories.map(c => ({ name: c.name, weight: c.weight }))
  )
  const [scale, setScale] = useState(
    gradeScale.map(s => ({ letter: s.letter, min_percent: s.minPercent, max_percent: s.maxPercent }))
  )
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await onSaveCategories(cats)
    await onSaveScale(scale)
    setSaving(false)
    onClose()
  }

  return (
    <div className="mb-4 p-4 bg-cream rounded-xl border border-border">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-display font-semibold text-sm text-primary">Category Weights</h4>
        <button onClick={onReparse} className="text-xs text-accent hover:text-accent-hover">
          Re-parse syllabus
        </button>
      </div>

      {/* Category weights */}
      <div className="space-y-1.5 mb-4">
        {cats.map((cat, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={cat.name}
              onChange={e => {
                const next = [...cats]
                next[i] = { ...next[i], name: e.target.value }
                setCats(next)
              }}
              className="flex-1 text-sm border border-border rounded px-2 py-1"
            />
            <input
              type="number"
              value={cat.weight}
              onChange={e => {
                const next = [...cats]
                next[i] = { ...next[i], weight: parseFloat(e.target.value) || 0 }
                setCats(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-sm text-muted">%</span>
            <button
              onClick={() => setCats(cats.filter((_, j) => j !== i))}
              className="text-xs text-muted hover:text-red-500"
            >{'\u2715'}</button>
          </div>
        ))}
        <button
          onClick={() => setCats([...cats, { name: '', weight: 0 }])}
          className="text-xs text-accent hover:text-accent-hover font-medium"
        >
          + Add category
        </button>
        <div className="text-xs text-muted mt-1">
          Total: {cats.reduce((s, c) => s + c.weight, 0)}%
        </div>
      </div>

      {/* Grade scale */}
      <h4 className="font-display font-semibold text-sm text-primary mb-2">Grade Scale</h4>
      <div className="space-y-1.5 mb-4">
        {scale.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="text"
              value={s.letter}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], letter: e.target.value }
                setScale(next)
              }}
              className="w-12 text-sm text-center border border-border rounded px-1 py-1"
            />
            <input
              type="number"
              value={s.min_percent}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], min_percent: parseFloat(e.target.value) || 0 }
                setScale(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-xs text-muted">-</span>
            <input
              type="number"
              value={s.max_percent ?? 100}
              onChange={e => {
                const next = [...scale]
                next[i] = { ...next[i], max_percent: parseFloat(e.target.value) || null }
                setScale(next)
              }}
              className="w-16 text-sm text-right border border-border rounded px-2 py-1"
            />
            <span className="text-xs text-muted">%</span>
            <button
              onClick={() => setScale(scale.filter((_, j) => j !== i))}
              className="text-xs text-muted hover:text-red-500"
            >{'\u2715'}</button>
          </div>
        ))}
        <button
          onClick={() => setScale([...scale, { letter: '', min_percent: 0, max_percent: null }])}
          className="text-xs text-accent hover:text-accent-hover font-medium"
        >
          + Add grade threshold
        </button>
      </div>

      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-1.5 bg-accent hover:bg-accent-hover text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button
          onClick={onClose}
          className="px-4 py-1.5 text-sm text-secondary hover:text-primary"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/GradeCalculator.tsx
git commit -m "feat: add GradeCalculator component with inline what-if editing"
```

---

### Task 8: Integration — Replace flat grades list with GradeCalculator in CoursesView

**Files:**
- Modify: `frontend/src/components/CoursesView.tsx`

- [ ] **Step 1: Add import for GradeCalculator**

At the top of `CoursesView.tsx`, add:

```typescript
import GradeCalculator from './GradeCalculator'
```

- [ ] **Step 2: Replace the flat grades section in CourseDetail**

In the `CourseDetail` component, find the entire grades section (the `<div className="mt-6 p-4 bg-sand rounded-xl">` block that contains the `Grades` header and assignment list). Replace it with:

```tsx
      {/* Grade Calculator */}
      <GradeCalculator courseId={course.id} />
```

Also remove the `grades` and `currentGrade` state variables and the `useEffect` that fetches them, since GradeCalculator handles its own data loading. The `CourseDetail` function should become:

```tsx
function CourseDetail({ course, tasks }: { course: Course; tasks: Task[] }) {
  return (
    <div>
      <h2 className="font-display font-bold text-xl text-primary">{course.code || course.name}</h2>
      <p className="text-secondary text-sm mt-1">{course.name}</p>

      {/* Syllabus Section */}
      <SyllabusPanel
        courseId={course.id}
        syllabusUrl={course.syllabus_url}
        syllabusText={course.syllabus_text}
        syllabusFile={course.syllabus_file}
      />

      {/* Grade Calculator */}
      <GradeCalculator courseId={course.id} />

      {/* Course info */}
      {course.instructor && (
        <div className="mt-4">
          <span className="text-muted text-sm">Instructor: </span>
          <span className="text-primary text-sm">{course.instructor}</span>
        </div>
      )}

      {/* Pending Assignments */}
      <div className="mt-6">
        <h3 className="font-display font-semibold text-xs text-muted uppercase tracking-wider mb-3">
          Pending Assignments ({tasks.length})
        </h3>
        {tasks.length === 0 ? (
          <p className="text-muted text-sm">No pending assignments.</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.id} className="p-3 bg-sand rounded-lg">
                <div className="flex items-center justify-between">
                  <p className="text-primary text-sm font-medium">{task.title}</p>
                  {task.current_grade && (
                    <span className="text-xs text-secondary">Grade: {task.current_grade}</span>
                  )}
                </div>
                {task.deadline && (
                  <p className="text-xs text-secondary mt-1">
                    Due: {new Date(task.deadline).toLocaleDateString('en-US', {
                      weekday: 'short', month: 'short', day: 'numeric',
                      hour: 'numeric', minute: '2-digit',
                    })}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {course.updated_at && (
        <p className="text-xs text-muted mt-6">
          Last synced: {new Date(course.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Remove unused imports**

Remove `apiFetch` from the imports at the top of CoursesView.tsx if it's no longer used by any other function in the file. Keep it only if `SyllabusPanel` or other functions still reference it. Also remove `useEffect` from react imports if no longer used.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CoursesView.tsx
git commit -m "feat: replace flat grades list with GradeCalculator in course detail"
```

---

### Task 9: Verification — Build frontend, verify no type errors

- [ ] **Step 1: Run TypeScript compiler check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no type errors. If there are errors, fix them in the relevant files.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

Expected: build succeeds with no errors.

- [ ] **Step 3: Verify backend imports**

```bash
cd /path/to/project && python -c "from src.planner.api.grade_calculator import router; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 4: Commit any fixes**

If any fixes were needed:

```bash
git add -A
git commit -m "fix: resolve type and build errors in grade calculator"
```
