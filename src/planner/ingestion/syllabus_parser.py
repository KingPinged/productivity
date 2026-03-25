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
