import json
from datetime import date as date_module
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.planner.db import PlannerDB

router = APIRouter(prefix="/api")

ai_scheduler = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


def _build_chat_prompt(message: str, db: PlannerDB) -> str:
    """Build the context-rich prompt for chat."""
    today = date_module.today().isoformat()
    context = ai_scheduler._context_builder.build(today)
    memories = db.search_memories(message, limit=5)
    blocks = db.get_schedule_blocks(today)

    chat_prompt = f"""You are the student's AI scheduling assistant. Answer their question based on the context below.
Use markdown formatting in your response — headers, bold, bullet points, etc.

Today is {context['day_of_week']}, {context['date']}.

## Current Schedule:
"""
    for b in blocks:
        chat_prompt += f"- {b['start_time']}-{b['end_time']}: {b['block_type']} ({b.get('ai_reason', '')})\n"

    tasks = context.get("tasks", [])
    if tasks:
        chat_prompt += "\n## Pending Tasks:\n"
        for t in tasks:
            line = f"- {t['title']}"
            if t.get("course"): line += f" [{t['course']}]"
            if t.get("deadline"): line += f" — due {t['deadline']}"
            if t.get("current_grade"): line += f" (grade: {t['current_grade']})"
            chat_prompt += line + "\n"

    grades = context.get("course_grades", [])
    if grades:
        chat_prompt += "\n## Course Grades:\n"
        for g in grades:
            chat_prompt += f"- {g['code'] or g['course']}: {g['current_grade']}\n"

    if memories:
        chat_prompt += "\n## Relevant Memories:\n"
        for m in memories:
            chat_prompt += f"- {m['content']}\n"

    events = context.get("events", [])
    if events:
        chat_prompt += "\n## Upcoming Events:\n"
        for e in events[:10]:
            chat_prompt += f"- {e['title']}: {e['start_time']} to {e['end_time']}\n"

    user_ctx = context.get("user_context", [])
    if user_ctx:
        chat_prompt += "\n## Student's Recent Context:\n"
        for c in user_ctx:
            chat_prompt += f"- \"{c['message']}\"\n"

    chat_prompt += f"\n## Student's Question:\n{message}\n\nAnswer helpfully and concisely using markdown formatting."

    return chat_prompt


@router.post("/chat")
def chat(body: dict, db: PlannerDB = Depends(get_db)):
    """Chat with the AI — returns a streaming SSE response."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Message is required"}

    if ai_scheduler is None:
        return {"error": "AI not configured", "response": "AI scheduler not available. Set your Anthropic API key in Settings."}

    chat_prompt = _build_chat_prompt(message, db)

    def generate():
        full_response = ""
        try:
            with ai_scheduler._client.messages.stream(
                model=ai_scheduler._model,
                max_tokens=1024,
                system="You are a helpful AI scheduling assistant for a college student. Answer their questions about their schedule, tasks, grades, and upcoming deadlines. Be friendly, concise, and actionable. Use markdown formatting — headers, bold, bullet points, etc.",
                messages=[{"role": "user", "content": chat_prompt}],
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield f"data: {json.dumps({'type': 'chunk', 'text': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Store memory after streaming completes
            db.add_memory(
                category="conversation",
                content=f"Student asked: '{message[:100]}'. Key point: {full_response[:100]}",
                importance=3,
            )

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
