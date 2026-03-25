# Grade Calculator Design

**Date:** 2026-03-25
**Target:** Feature branch `feat/ai-scheduling-assistant-phase1` (React + FastAPI web app)
**Source reference:** `canvasGet` repo grade calculation logic

## Overview

Add a grade calculator to the courses tab that computes weighted grades from syllabus category weights and current assignment scores. Supports inline what-if editing for scenario modeling. Syllabus weight/scale data is auto-parsed from stored syllabus text with manual override capability.

## Backend Schema Extensions

### New Tables

**`grade_categories`** — Per-course category weights from syllabus.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| course_id | INTEGER FK | References courses(id) |
| name | TEXT | Category name (e.g., "Homework") |
| weight | REAL | Percentage weight (0-100) |
| source | TEXT | "auto" or "manual" — tracks origin |

**`grade_scales`** — Per-course letter grade thresholds.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| course_id | INTEGER FK | References courses(id) |
| letter | TEXT | Grade letter (e.g., "A", "B+") |
| min_percent | REAL | Lower bound (inclusive) |
| max_percent | REAL | Upper bound (exclusive, nullable for top) |

### Existing Table Changes

**`grades`** — Add column:

| Column | Type | Notes |
|--------|------|-------|
| category | TEXT | Nullable. Maps assignment to a grade_category name |

## Backend: Syllabus Auto-Parsing

Port canvasGet's regex extraction to Python in a new module `src/planner/ingestion/syllabus_parser.py`.

### `extract_grade_weights(text: str) -> list[dict]`

Scans syllabus text for patterns:
- "Homework 30%", "Exams: 40%", "30% Homework"
- Known category keywords: homework, assignments, quizzes, exams, midterms, finals, participation, attendance, labs, projects, papers, essays, discussion, presentations, classwork, readings, problem sets

Returns `[{"category": str, "weight": str}]`.

### `extract_grade_scale(text: str) -> list[dict]`

Scans for patterns:
- "A: 90-100", "A = 93-100", "A >= 90", "90-100 A"

Returns deduplicated, sorted `[{"letter": str, "min_percent": float, "max_percent": float | None}]`.

### Trigger

- Runs automatically during Canvas sync after syllabus text is stored
- Only populates tables if empty for that course (preserves manual edits)
- "Re-parse syllabus" button in UI can re-trigger via API

### Category Mapping

After parsing weights, fuzzy-match existing `grades` rows to categories by comparing assignment names and Canvas assignment group names against parsed category names. Unmatched assignments go to "Uncategorized".

## Backend: Grade Calculation API

### `GET /api/courses/{course_id}/grade-calculator`

Returns computed grade breakdown:

```json
{
  "categories": [
    {
      "name": "Homework",
      "weight": 25.0,
      "earned": 290,
      "possible": 300,
      "score": 96.7,
      "assignments": [
        { "id": 1, "name": "HW 1", "score": "90", "points_possible": "100" },
        { "id": 2, "name": "HW 2", "score": null, "points_possible": "100" }
      ]
    }
  ],
  "weightedGrade": 72.3,
  "letterGrade": "C-",
  "gradeScale": [
    { "letter": "A", "minPercent": 93, "maxPercent": 100 }
  ]
}
```

**Calculation logic:**
1. Group graded assignments by category
2. Per category: `score = totalEarned / totalPossible * 100`
3. Weighted grade: `sum(categoryScore * categoryWeight / 100)` normalized by sum of weights for categories that have graded work (ungraded categories don't count)
4. Map weighted grade to letter via grade scale thresholds

### `POST /api/courses/{course_id}/grade-calculator/simulate`

Accepts hypothetical overrides, returns same shape with hypotheticals applied. Stateless (nothing saved).

```json
{
  "overrides": [
    { "grade_id": 5, "score": "95" },
    { "grade_id": null, "category": "Exam 2", "score": "88", "points_possible": "100" }
  ]
}
```

### `PUT /api/courses/{course_id}/grade-categories`

Bulk update category weights. Body: `{"categories": [{"name": str, "weight": float}]}`.

### `PUT /api/courses/{course_id}/grade-scale`

Bulk update grade scale. Body: `{"scale": [{"letter": str, "min_percent": float, "max_percent": float | null}]}`.

### `POST /api/courses/{course_id}/reparse-syllabus`

Re-run syllabus auto-parsing, overwriting existing auto-parsed data (preserves manual entries).

## Frontend: Grade Calculator UI

Replaces the current flat grades list in `CourseDetail` component.

### Category Breakdown View

Each category is a collapsible section:
- Header: category name + weight badge (e.g., "Homework -- 25%") + category average
- Body: list of assignments with score / points_possible

### Inline What-If Editing

- Click any assignment score to edit it inline
- Ungraded assignments show a dashed placeholder, clickable to enter hypothetical
- Modified scores get a visual indicator (colored border) showing they're hypothetical
- Category averages and weighted grade recalculate live in the browser (client-side JS, no server round-trip)
- "Reset" button clears all hypotheticals

### Overall Grade Display

At the top of the grade calculator section:
- Weighted percentage (large, prominent)
- Letter grade badge (from grade scale)
- Both update live during what-if editing

### Editable Weights and Scale

Gear icon opens inline editor for:
- Category weights (pre-populated from auto-parse, user can correct)
- Grade scale thresholds
- Saves via PUT endpoints

### Add Hypothetical Assignments

"+ Add assignment" link at the bottom of each category:
- Enter score and points_possible
- Simulation-only, not persisted
- Included in live recalculation

### Calculation (Client-Side)

All grade computation happens in a pure function in the frontend for instant feedback:

```typescript
function computeWeightedGrade(
  categories: CategoryWithAssignments[],
  overrides: Map<number | string, { score: number; possible: number }>
): { weightedGrade: number; categoryScores: Map<string, number> }
```

1. Apply overrides to assignment scores
2. Per category: sum earned / sum possible
3. Weighted average normalized by active weight sum
4. Map to letter grade

## File Changes Summary

### New Files
- `src/planner/ingestion/syllabus_parser.py` — regex extraction functions
- `src/planner/api/grade_calculator.py` — new API router
- `frontend/src/components/GradeCalculator.tsx` — main UI component
- `frontend/src/hooks/useGradeCalculator.ts` — data fetching + client-side computation

### Modified Files
- `src/planner/db.py` — new tables, new queries, grades.category column
- `src/planner/server.py` — register new router
- `src/planner/ingestion/canvas_requests.py` — trigger syllabus parsing on sync, store assignment categories
- `frontend/src/components/CoursesView.tsx` — replace flat grades section with GradeCalculator
- `frontend/src/types/index.ts` — new type definitions
