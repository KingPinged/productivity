import json
import logging
from datetime import date as date_module, datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from src.planner.db import PlannerDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

ai_scheduler = None


def get_db():
    raise NotImplementedError("Override via app.dependency_overrides")


# Tools the AI can call
TOOLS = [
    {
        "name": "add_context",
        "description": "Save a piece of context about the student's situation (e.g., 'feeling burnt out', 'skipping class'). Use this when the student tells you something about their state, plans, or preferences.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The context to save"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "replan_schedule",
        "description": "Regenerate today's schedule based on current context. Call this after adding context that would change the schedule.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date to replan (YYYY-MM-DD). Defaults to today."},
            },
        },
    },
    {
        "name": "add_task",
        "description": "Add a new task/to-do to the student's task list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "deadline": {"type": "string", "description": "Due date (ISO format or natural language)"},
                "course": {"type": "string", "description": "Course name if academic"},
                "estimated_minutes": {"type": "integer", "description": "Estimated time in minutes"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "Mark a task as completed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_title": {"type": "string", "description": "Title of the task to complete (partial match OK)"},
            },
            "required": ["task_title"],
        },
    },
    {
        "name": "save_memory",
        "description": "Save an important fact to long-term memory for future sessions. Use for preferences, recurring patterns, important dates, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact to remember"},
                "category": {"type": "string", "enum": ["preference", "academic", "health", "social", "schedule"], "description": "Category of memory"},
                "importance": {"type": "integer", "description": "1-10 importance scale", "default": 5},
            },
            "required": ["content", "category"],
        },
    },
    {
        "name": "get_schedule",
        "description": "Get the current schedule for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date (YYYY-MM-DD). Defaults to today."},
            },
        },
    },
    {
        "name": "get_grades",
        "description": "Get the student's current grades across all courses.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "search_memory",
        "description": "Search past memories and interactions for relevant information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
]


def _execute_tool(tool_name: str, tool_input: dict, db: PlannerDB) -> str:
    """Execute a tool call and return the result as a string."""
    today = date_module.today().isoformat()

    if tool_name == "add_context":
        db.add_user_context(tool_input["message"])
        return f"Saved context: \"{tool_input['message']}\""

    elif tool_name == "replan_schedule":
        target = tool_input.get("date", today)
        if ai_scheduler:
            result = ai_scheduler.replan(target)
            if result:
                count = len(result.get("schedule", []))
                return f"Replanned schedule for {target}: {count} blocks generated."
            return "Replan failed — check API key."
        return "AI scheduler not available."

    elif tool_name == "add_task":
        import secrets
        tid = db.upsert_task(
            source="manual",
            external_id=f"manual:{secrets.token_urlsafe(8)}",
            title=tool_input["title"],
            deadline=tool_input.get("deadline"),
            course=tool_input.get("course"),
            estimated_minutes=tool_input.get("estimated_minutes"),
        )
        return f"Added task: \"{tool_input['title']}\" (id={tid})"

    elif tool_name == "complete_task":
        search = tool_input["task_title"].lower()
        tasks = db.get_tasks(status="pending")
        for t in tasks:
            if search in t["title"].lower():
                db.update_task_status(t["id"], "done")
                return f"Marked \"{t['title']}\" as complete."
        return f"Could not find a pending task matching \"{tool_input['task_title']}\"."

    elif tool_name == "save_memory":
        db.add_memory(
            category=tool_input["category"],
            content=tool_input["content"],
            importance=tool_input.get("importance", 5),
        )
        return f"Saved to memory: \"{tool_input['content']}\""

    elif tool_name == "get_schedule":
        target = tool_input.get("date", today)
        blocks = db.get_schedule_blocks(target)
        if not blocks:
            return f"No schedule blocks for {target}."
        lines = [f"Schedule for {target}:"]
        for b in blocks:
            lines.append(f"- {b['start_time']}-{b['end_time']}: {b['block_type']} ({b.get('ai_reason', '')})")
        return "\n".join(lines)

    elif tool_name == "get_grades":
        courses = db.get_courses()
        if not courses:
            return "No courses found."
        lines = ["Current grades:"]
        for c in courses:
            grade = c.get("current_grade", "N/A")
            lines.append(f"- {c.get('code') or c['name']}: {grade}")
        return "\n".join(lines)

    elif tool_name == "search_memory":
        memories = db.search_memories(tool_input["query"], limit=10)
        if not memories:
            return f"No memories found matching \"{tool_input['query']}\"."
        lines = [f"Found {len(memories)} memories:"]
        for m in memories:
            lines.append(f"- [{m['category']}] {m['content']}")
        return "\n".join(lines)

    return f"Unknown tool: {tool_name}"


def _build_context_summary(db: PlannerDB) -> str:
    """Build a compact context summary for the AI."""
    today = date_module.today().isoformat()
    context = ai_scheduler._context_builder.build(today)

    parts = [f"Today is {context['day_of_week']}, {context['date']}."]

    # Schedule
    blocks = db.get_schedule_blocks(today)
    if blocks:
        parts.append("\nCurrent schedule:")
        for b in blocks:
            parts.append(f"- {b['start_time']}-{b['end_time']}: {b['block_type']} ({b.get('ai_reason', '')})")

    # Tasks (compact)
    tasks = context.get("tasks", [])
    if tasks:
        parts.append(f"\n{len(tasks)} pending tasks. Nearest deadlines:")
        for t in sorted(tasks, key=lambda x: x.get("deadline") or "9")[:5]:
            line = f"- {t['title']}"
            if t.get("course"): line += f" [{t['course']}]"
            if t.get("deadline"): line += f" due {t['deadline']}"
            parts.append(line)

    # Grades
    grades = context.get("course_grades", [])
    if grades:
        parts.append("\nGrades: " + ", ".join(f"{g['code'] or g['course']}: {g['current_grade']}" for g in grades))

    # Recent context
    user_ctx = context.get("user_context", [])
    if user_ctx:
        parts.append("\nStudent recently said: " + "; ".join(f'"{c["message"]}"' for c in user_ctx[:5]))

    # Memories
    memories = context.get("memories", [])
    if memories:
        parts.append("\nMemories: " + "; ".join(m["content"] for m in memories[:5]))

    return "\n".join(parts)


SYSTEM = """You are a college student's AI scheduling assistant with access to tools. You can take ACTIONS, not just answer questions.

When the student tells you something (even if it's not a question), respond helpfully:
- If they tell you about their day/state → use add_context + replan_schedule, then tell them what changed
- If they want to add something → use add_task
- If they finished something → use complete_task + replan_schedule
- If they ask a question → use get_schedule, get_grades, or search_memory to look up info, then answer
- If they share a preference or important fact → use save_memory

ALWAYS respond with a friendly, concise message after using tools. Use markdown formatting.
Examples of good responses after actions:
- "Got it! I've noted that you're skipping office hours and replanned your afternoon. You now have a study block from 2-4pm for Probability I instead."
- "Done! Added 'Study for midterm' to your tasks. I'll work it into tomorrow's schedule."
- "I remember! Last week you mentioned struggling with proofs — I've been scheduling extra Probability I time because of that."

Be conversational, warm, and proactive. You're not just a tool — you're a helpful companion."""


@router.post("/chat")
def chat(body: dict, db: PlannerDB = Depends(get_db)):
    """Chat with the AI using tool calling and streaming."""
    message = body.get("message", "").strip()
    if not message:
        return {"error": "Message is required"}

    if ai_scheduler is None:
        return {"error": "AI not configured", "response": "Set your Anthropic API key in Settings."}

    context_summary = _build_context_summary(db)

    def generate():
        try:
            messages = [{"role": "user", "content": f"{context_summary}\n\n---\n\nStudent: {message}"}]
            tool_results_text = []

            # Loop for tool calling — AI may call multiple tools before responding
            for _ in range(5):  # Max 5 tool call rounds
                response = ai_scheduler._client.messages.create(
                    model=ai_scheduler._model,
                    max_tokens=1024,
                    system=SYSTEM,
                    messages=messages,
                    tools=TOOLS,
                )

                # Check if the AI wants to call tools
                tool_calls = [b for b in response.content if b.type == "tool_use"]

                if not tool_calls:
                    # No tools — just text response, stream it
                    break

                # Execute each tool call
                tool_results = []
                for tc in tool_calls:
                    result = _execute_tool(tc.name, tc.input, db)
                    tool_results_text.append(f"*Used {tc.name}*")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc.id,
                        "content": result,
                    })
                    logger.info("Tool %s(%s) -> %s", tc.name, json.dumps(tc.input)[:100], result[:100])

                # Send tool results back and continue
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

            # Now stream the final text response
            # Send tool action indicators first
            if tool_results_text:
                actions = " | ".join(tool_results_text)
                yield f"data: {json.dumps({'type': 'actions', 'text': actions})}\n\n"

            # Stream the final response
            with ai_scheduler._client.messages.stream(
                model=ai_scheduler._model,
                max_tokens=1024,
                system=SYSTEM,
                messages=messages,
            ) as stream:
                full_response = ""
                for text in stream.text_stream:
                    full_response += text
                    yield f"data: {json.dumps({'type': 'chunk', 'text': text})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Save memory
            db.add_memory(
                category="conversation",
                content=f"Student: '{message[:80]}'. AI action: {', '.join(tool_results_text) if tool_results_text else 'answered'}. Response: {full_response[:80]}",
                importance=3,
            )

        except Exception as e:
            logger.error("Chat error: %s", e)
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
