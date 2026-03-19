SYSTEM_PROMPT = """You are an AI scheduling assistant for a college student. Your job is to create an optimal daily schedule as time-blocked entries.

Rules:
1. Schedule within the user's wake/sleep window only.
2. Never overlap blocks with existing calendar events.
3. Insert break blocks: 15 minutes every 90 minutes of work (or per user preference).
4. Prioritize by: deadline proximity × grade impact. Lower grades = more study time.
5. Schedule demanding work during peak hours (typically morning/early afternoon).
6. Place lighter tasks (emails, organizing) in low-energy windows.
7. No block should exceed 2 hours without a break.
8. Account for completed blocks — don't reschedule what's done.

Output ONLY valid JSON matching this schema:
{
  "schedule": [
    {
      "start": "HH:MM",
      "end": "HH:MM",
      "task": "Task name or 'Break'",
      "type": "study|meeting|rest|personal|buffer",
      "priority": "high|medium|low",
      "reason": "Brief explanation"
    }
  ],
  "tasks_today": ["Task names to complete today"],
  "tasks_later": ["Task names deferred to future days"],
  "reminders": [
    {"time": "HH:MM", "message": "Reminder text", "urgent": true/false}
  ]
}

Do not include any text before or after the JSON."""


def build_user_prompt(context: dict) -> str:
    parts = []
    parts.append(f"Today is {context['day_of_week']}, {context['date']}.")

    prefs = context.get("preferences", {})
    wake = prefs.get("wake_time", "07:00")
    sleep = prefs.get("sleep_time", "23:00")
    max_hours = prefs.get("max_work_hours", "8")
    break_freq = prefs.get("break_frequency", "90")
    style = prefs.get("schedule_style", "balanced")

    parts.append(f"\nSchedule window: {wake} to {sleep}")
    parts.append(f"Max work hours: {max_hours}")
    parts.append(f"Break every {break_freq} minutes")
    parts.append(f"Schedule style: {style}")

    events = context.get("events", [])
    if events:
        parts.append("\n## Fixed Calendar Events (do not schedule over these):")
        for e in events:
            parts.append(f"- {e['title']}: {e['start_time']} to {e['end_time']} ({e['event_type']})")

    tasks = context.get("tasks", [])
    if tasks:
        parts.append("\n## Pending Tasks:")
        for t in tasks:
            line = f"- {t['title']}"
            if t.get("course"):
                line += f" [{t['course']}]"
            if t.get("deadline"):
                line += f" — due {t['deadline']}"
            if t.get("estimated_minutes"):
                line += f" (~{t['estimated_minutes']} min)"
            if t.get("current_grade"):
                line += f" (current grade: {t['current_grade']})"
            parts.append(line)

    completed = context.get("completed_today", [])
    if completed:
        parts.append("\n## Already Completed Today:")
        for c in completed:
            parts.append(f"- {c['block_type']}: {c['start_time']} to {c['end_time']}")

    parts.append("\nCreate an optimized schedule for the rest of today.")
    return "\n".join(parts)
