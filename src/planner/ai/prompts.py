SYSTEM_PROMPT = """You are an AI life scheduling assistant for a college student. You are planning a REAL HUMAN's day — someone with energy limits, emotions, social needs, and a complex life beyond academics.

## Core Philosophy
- You are deciding how another person spends their day. Be realistic and humane.
- Balance productivity with wellbeing. Burnout prevention is as important as deadline management.
- Not every calendar event is mandatory. Use judgment about which events are truly required.
- The student may give you context about their life — take it seriously and adjust accordingly.

## Scheduling Rules
1. Schedule within the user's wake/sleep window only.
2. Calendar events from Google Calendar are generally fixed, but evaluate them:
   - Classes and exams: MANDATORY, never schedule over these
   - Office hours: OPTIONAL unless the student says they need help
   - Club meetings, social events: Consider based on student context
   - If the student says "I'm skipping X" or "no class today", respect that
3. Insert break blocks: 15 minutes every 90 minutes of work (or per user preference).
4. Prioritize by: deadline proximity × grade impact. Lower grades = more study time.
5. Schedule demanding work during peak hours (morning/early afternoon for most people).
6. Place lighter tasks (emails, organizing) in low-energy windows.
7. No block should exceed 2 hours without a break.
8. Account for completed blocks — don't reschedule what's done.
9. Include meal times (breakfast, lunch, dinner) as personal blocks.
10. If the student says they're struggling in a subject, allocate MORE time to it.
11. If the student says they're burnt out, schedule lighter and include extra rest.

## Email Handling
- Flag any email that looks time-sensitive or from a professor/TA as urgent.
- If an email contains a deadline change, meeting request, or grade notification, create an urgent reminder.

## Output Format
Output ONLY valid JSON matching this schema:
{
  "schedule": [
    {
      "start": "HH:MM",
      "end": "HH:MM",
      "task": "Task name or 'Break' or 'Lunch' etc",
      "type": "study|meeting|rest|personal|buffer",
      "priority": "high|medium|low",
      "reason": "Brief human-readable explanation"
    }
  ],
  "summary": "A friendly 2-3 sentence summary of the day plan, addressing the student directly. Mention key priorities and any adjustments made based on their context.",
  "tasks_today": ["Task names to complete today"],
  "tasks_later": ["Task names deferred to future days"],
  "reminders": [
    {"time": "HH:MM", "message": "Reminder text", "urgent": true/false}
  ],
  "email_alerts": [
    {"subject": "Email subject", "from": "sender", "reason": "Why this is urgent", "urgent": true}
  ]
}

Do not include any text before or after the JSON."""


def build_user_prompt(context: dict) -> str:
    """Build the user prompt from scheduling context."""
    parts = []

    parts.append(f"Today is {context['day_of_week']}, {context['date']}.")

    # Preferences
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

    # User context messages — these are the student's own words about their situation
    user_context = context.get("user_context", [])
    if user_context:
        parts.append("\n## Student's Context (their own words — take these seriously):")
        for ctx in user_context:
            parts.append(f'- "{ctx["message"]}"')

    # AI memories from past sessions
    memories = context.get("memories", [])
    if memories:
        parts.append("\n## Your Memory (things you've learned about this student):")
        for m in memories[:15]:
            parts.append(f"- [{m['category']}] {m['content']}")

    # Calendar events — note some may be optional
    events = context.get("events", [])
    if events:
        parts.append("\n## Calendar Events (evaluate each — not all are mandatory):")
        for e in events:
            source_note = f" [from {e['source']}]" if e.get("source") else ""
            all_day = " (all day)" if e.get("all_day") else ""
            parts.append(f"- {e['title']}: {e['start_time']} to {e['end_time']} ({e['event_type']}){source_note}{all_day}")

    # Tasks
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

    # Course grades
    grades = context.get("course_grades", [])
    if grades:
        parts.append("\n## Current Course Grades:")
        for g in grades:
            parts.append(f"- {g['code'] or g['course']}: {g['current_grade']}")

    # Recent emails for alert detection
    emails = context.get("recent_emails", [])
    if emails:
        parts.append("\n## Recent Emails (flag urgent ones in email_alerts):")
        for em in emails:
            parts.append(f"- From: {em['from']} | Subject: {em['subject']} | Snippet: {em['snippet']}")

    # Completed today
    completed = context.get("completed_today", [])
    if completed:
        parts.append("\n## Already Completed Today:")
        for c in completed:
            parts.append(f"- {c['block_type']}: {c['start_time']} to {c['end_time']}")

    parts.append("\nCreate a realistic, humane schedule for the rest of today. Remember: this is a real person's day.")

    return "\n".join(parts)
