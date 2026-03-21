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
    {
        "name": "add_calendar_event",
        "description": "Add a new event to the calendar (gym, appointment, social event, etc). This creates a visible calendar event, not just a schedule block.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title (e.g., 'Gym', 'Doctor appointment')"},
                "date": {"type": "string", "description": "Date (YYYY-MM-DD). Defaults to today."},
                "start_time": {"type": "string", "description": "Start time (HH:MM in 24h format)"},
                "end_time": {"type": "string", "description": "End time (HH:MM in 24h format)"},
                "event_type": {"type": "string", "description": "Type: meeting, personal, class, other", "default": "personal"},
            },
            "required": ["title", "start_time", "end_time"],
        },
    },
    {
        "name": "edit_calendar_event",
        "description": "Edit an existing calendar event's time or title. Search by title to find it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_title": {"type": "string", "description": "Title to search for (partial match)"},
                "new_title": {"type": "string", "description": "New title (optional)"},
                "new_start_time": {"type": "string", "description": "New start time HH:MM (optional)"},
                "new_end_time": {"type": "string", "description": "New end time HH:MM (optional)"},
            },
            "required": ["search_title"],
        },
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete a calendar event by title (partial match).",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_title": {"type": "string", "description": "Title to search for (partial match)"},
            },
            "required": ["search_title"],
        },
    },
]


def _to_12h(time_str: str) -> str:
    """Convert HH:MM to 12h format."""
    try:
        h, m = time_str.split(":")
        h = int(h)
        ampm = "AM" if h < 12 else "PM"
        if h == 0: h = 12
        elif h > 12: h -= 12
        return f"{h}:{m} {ampm}"
    except Exception:
        return time_str


def _next_day(date_str: str) -> str:
    """Get the next day as YYYY-MM-DD."""
    from datetime import timedelta
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d")


def _execute_tool(tool_name: str, tool_input: dict, db: PlannerDB) -> str:
    """Execute a tool call and return the result as a string."""
    today = _get_central_time().strftime("%Y-%m-%d")

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
        # Also get calendar events for the date
        events = db.get_events(start_after=target, end_before=_next_day(target))
        if not blocks and not events:
            return f"No schedule blocks or events for {target}."
        lines = [f"Schedule for {target}:"]
        for b in blocks:
            start_12 = _to_12h(b['start_time'])
            end_12 = _to_12h(b['end_time'])
            status_tag = f" [{b['status']}]" if b['status'] != 'scheduled' else ""
            lines.append(f"- {start_12}-{end_12}: {b['block_type']} ({b.get('ai_reason', '')}){status_tag}")
        if events:
            lines.append("\nCalendar events:")
            for e in events:
                lines.append(f"- {e['title']}: {e['start_time']} to {e['end_time']} ({e.get('event_type', '')})")
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

    elif tool_name == "add_calendar_event":
        import secrets
        target_date = tool_input.get("date", today)
        start = f"{target_date}T{tool_input['start_time']}:00"
        end = f"{target_date}T{tool_input['end_time']}:00"
        eid = db.upsert_event(
            account_id=None,
            source="manual",
            external_id=f"manual:{secrets.token_urlsafe(8)}",
            title=tool_input["title"],
            start_time=start,
            end_time=end,
            event_type=tool_input.get("event_type", "personal"),
        )
        return f"Added calendar event: \"{tool_input['title']}\" on {target_date} from {tool_input['start_time']} to {tool_input['end_time']} (id={eid})"

    elif tool_name == "edit_calendar_event":
        search = tool_input["search_title"].lower()
        events = db.get_events()
        for e in events:
            if search in e["title"].lower():
                updates = {}
                new_title = tool_input.get("new_title") or e["title"]
                new_start = e["start_time"]
                new_end = e["end_time"]
                if tool_input.get("new_start_time"):
                    date_part = e["start_time"][:10] if e["start_time"] and len(e["start_time"]) > 10 else today
                    new_start = f"{date_part}T{tool_input['new_start_time']}:00"
                if tool_input.get("new_end_time"):
                    date_part = e["end_time"][:10] if e["end_time"] and len(e["end_time"]) > 10 else today
                    new_end = f"{date_part}T{tool_input['new_end_time']}:00"
                db.upsert_event(
                    account_id=e.get("account_id", 0),
                    source=e["source"],
                    external_id=e["external_id"],
                    title=new_title,
                    start_time=new_start,
                    end_time=new_end,
                    event_type=e.get("event_type"),
                )
                return f"Updated event \"{e['title']}\" -> title=\"{new_title}\", {new_start} to {new_end}"
        return f"Could not find event matching \"{tool_input['search_title']}\"."

    elif tool_name == "delete_calendar_event":
        search = tool_input["search_title"].lower()
        events = db.get_events()
        for e in events:
            if search in e["title"].lower():
                conn = db._get_conn()
                conn.execute("DELETE FROM events WHERE id = ?", (e["id"],))
                conn.commit()
                return f"Deleted event: \"{e['title']}\""
        return f"Could not find event matching \"{tool_input['search_title']}\"."

    return f"Unknown tool: {tool_name}"


def _get_central_time():
    """Get current time in US Central timezone."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Chicago"))


def _build_context_summary(db: PlannerDB) -> str:
    """Build a lightweight context summary. Does NOT include schedule — AI must call get_schedule for fresh data."""
    now = _get_central_time()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%I:%M %p")
    day_of_week = now.strftime("%A")
    parts = [f"Today is {day_of_week}, {today}. The current time is {current_time} Central Time."]
    parts.append("IMPORTANT: Use get_schedule tool to look up the actual current schedule. Do NOT guess or use stale data.")

    # Grades (compact, stable data)
    courses = db.get_courses()
    if courses:
        grade_strs = [f"{c.get('code') or c['name']}: {c.get('current_grade', 'N/A')}" for c in courses]
        parts.append("\nGrades: " + ", ".join(grade_strs))

    # Recent context
    user_ctx = db.get_active_context()
    if user_ctx:
        parts.append("\nStudent recently said: " + "; ".join(f'"{c["message"]}"' for c in user_ctx[:5]))

    # Memories (compact)
    memories = db.get_memories(limit=10)
    if memories:
        parts.append("\nMemories: " + "; ".join(m["content"] for m in memories[:5]))

    return "\n".join(parts)


CHAT_MODEL = "claude-haiku-4-5-20251001"  # Fast model for chat, Sonnet for scheduling

SYSTEM = """You are a college student's AI scheduling assistant with tools. You take ACTIONS and answer questions.

CRITICAL RULES:
1. NEVER output HTML. Only use markdown (headers, bold, bullets, etc).
2. ALWAYS call get_schedule before answering questions about the schedule. NEVER guess schedule data from memory or context — always fetch fresh data.
3. Use 12-hour time format (e.g., "2:00 PM" not "14:00").
4. The student is in US Central Time (CT). All times you mention should be in Central Time.
5. When the student asks about their schedule, events, or "what do I have", call get_schedule FIRST, then answer based on the tool result.

When the student tells you something:
- About their day/state → add_context + replan_schedule, tell them what changed
- Add something → add_task or add_calendar_event
- Finished something → complete_task + replan_schedule
- Question about schedule/events → get_schedule (REQUIRED), then answer
- Question about grades → get_grades (REQUIRED), then answer
- Question about past events → search_memory, then answer
- Preference or important fact → save_memory

After using tools, respond with a friendly markdown-formatted message. Be concise and actionable. Keep responses SHORT — 2-4 sentences for simple queries, bullet points for lists."""


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
            for _ in range(3):  # Max 3 tool call rounds for speed
                response = ai_scheduler._client.messages.create(
                    model=CHAT_MODEL,
                    max_tokens=512,
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
                model=CHAT_MODEL,
                max_tokens=512,
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
