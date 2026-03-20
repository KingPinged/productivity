import json
from datetime import date as date_module
from fastapi import APIRouter, Depends

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

ai_scheduler = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


@router.post("/chat")
def chat(body: dict, db: PlannerDB = Depends(get_db)):
    """Chat with the AI — ask questions, get info, or give context."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Message is required"}

    if ai_scheduler is None:
        return {"error": "AI not configured", "response": "AI scheduler not available. Set your Anthropic API key in Settings."}

    # Build context for the AI to answer
    today = date_module.today().isoformat()
    context = ai_scheduler._context_builder.build(today)

    # Search memories for relevant info
    memories = db.search_memories(message, limit=5)

    # Get recent schedule
    blocks = db.get_schedule_blocks(today)

    # Build a focused prompt for Q&A
    from src.planner.ai.prompts import SYSTEM_PROMPT
    import anthropic

    chat_prompt = f"""You are the student's AI scheduling assistant. Answer their question based on the context below.

Today is {context['day_of_week']}, {context['date']}.

## Current Schedule:
"""
    for b in blocks:
        chat_prompt += f"- {b['start_time']}-{b['end_time']}: {b['block_type']} ({b.get('ai_reason', '')})\n"

    # Add tasks
    tasks = context.get("tasks", [])
    if tasks:
        chat_prompt += "\n## Pending Tasks:\n"
        for t in tasks:
            line = f"- {t['title']}"
            if t.get("course"): line += f" [{t['course']}]"
            if t.get("deadline"): line += f" — due {t['deadline']}"
            if t.get("current_grade"): line += f" (grade: {t['current_grade']})"
            chat_prompt += line + "\n"

    # Add grades
    grades = context.get("course_grades", [])
    if grades:
        chat_prompt += "\n## Course Grades:\n"
        for g in grades:
            chat_prompt += f"- {g['code'] or g['course']}: {g['current_grade']}\n"

    # Add relevant memories
    if memories:
        chat_prompt += "\n## Relevant Memories:\n"
        for m in memories:
            chat_prompt += f"- {m['content']}\n"

    # Add events
    events = context.get("events", [])
    if events:
        chat_prompt += "\n## Upcoming Events:\n"
        for e in events[:10]:
            chat_prompt += f"- {e['title']}: {e['start_time']} to {e['end_time']}\n"

    # Add user context
    user_ctx = context.get("user_context", [])
    if user_ctx:
        chat_prompt += "\n## Student's Recent Context:\n"
        for c in user_ctx:
            chat_prompt += f"- \"{c['message']}\"\n"

    chat_prompt += f"\n## Student's Question:\n{message}\n\nAnswer helpfully and concisely. If they're asking about something you don't have data for, say so honestly."

    try:
        response = ai_scheduler._client.messages.create(
            model=ai_scheduler._model,
            max_tokens=1024,
            system="You are a helpful AI scheduling assistant for a college student. Answer their questions about their schedule, tasks, grades, and upcoming deadlines. Be friendly, concise, and actionable.",
            messages=[{"role": "user", "content": chat_prompt}],
        )

        ai_response = response.content[0].text

        # Store this interaction as a memory
        db.add_memory(
            category="conversation",
            content=f"Student asked: '{message[:100]}'. Key point from answer: {ai_response[:100]}",
            importance=3,
        )

        return {"response": ai_response}

    except Exception as e:
        return {"error": str(e), "response": "Sorry, I couldn't process that right now."}
