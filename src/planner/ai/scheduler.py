import json
import logging
import time

import anthropic

from src.planner.ai.context_builder import ContextBuilder
from src.planner.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from src.planner.db import PlannerDB

logger = logging.getLogger(__name__)

REQUIRED_KEYS = {"schedule", "tasks_today", "tasks_later", "reminders"}
MAX_RETRIES = 2
BACKOFF_DELAYS = [5, 15, 60]


class AIScheduler:
    """Core AI scheduling engine using Claude API."""

    def __init__(self, db: PlannerDB, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._db = db
        self._api_key = api_key
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._context_builder = ContextBuilder(db)

    def generate(self, date: str) -> dict | None:
        """Generate a full schedule for the given date. Returns parsed result or None."""
        context = self._context_builder.build(date)
        context_hash = self._context_builder.compute_hash(context)

        # Check cache — skip if context hasn't changed
        cached = self._db.get_ai_cache(date)
        if cached and cached["context_hash"] == context_hash:
            logger.info("Context unchanged for %s, using cached schedule", date)
            try:
                return json.loads(cached["schedule_json"])
            except Exception:
                pass

        base_prompt = build_user_prompt(context)

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Build prompt with retry prefix if needed (fresh each attempt)
                retry_prefix = ""
                if attempt > 0:
                    retry_prefix = "IMPORTANT: Your previous response had issues. "

                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": retry_prefix + base_prompt}],
                )

                raw_text = response.content[0].text
                tokens_used = response.usage.input_tokens + response.usage.output_tokens

                result = self.parse_response(raw_text)
                if result is None:
                    if attempt < MAX_RETRIES:
                        logger.warning("Invalid JSON from Claude, retrying (%d/%d)", attempt + 1, MAX_RETRIES)
                        continue
                    logger.error("Failed to get valid JSON after %d attempts", MAX_RETRIES + 1)
                    return None

                if self.has_overlaps(result["schedule"]):
                    if attempt < MAX_RETRIES:
                        logger.warning("Schedule has overlaps, retrying (%d/%d)", attempt + 1, MAX_RETRIES)
                        continue
                    logger.warning("Schedule still has overlaps after retries, accepting anyway")

                # Cache the result
                self._db.save_ai_cache(date, context_hash, json.dumps(result), tokens_used)
                return result

            except anthropic.RateLimitError:
                delay = BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)]
                logger.warning("Rate limited, backing off %ds", delay)
                time.sleep(delay)
            except anthropic.APIError as e:
                logger.error("Claude API error: %s", e)
                if attempt < MAX_RETRIES:
                    time.sleep(BACKOFF_DELAYS[min(attempt, len(BACKOFF_DELAYS) - 1)])
                    continue
                return None

        return None

    def replan(self, date: str) -> dict | None:
        """Force a replan for the given date, ignoring cache. Stores result in DB."""
        context = self._context_builder.build(date)
        context_hash = self._context_builder.compute_hash(context)
        user_prompt = build_user_prompt(context)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw_text = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens

            result = self.parse_response(raw_text)
            if result is None:
                return None

            self._db.save_ai_cache(date, context_hash, json.dumps(result), tokens_used)
            self.store_schedule(date, result)

            context = self._context_builder.build(date)
            self._extract_and_store_memories(date, result, context.get("user_context", []))

            return result

        except Exception as e:
            logger.error("Replan failed: %s", e)
            return None

    def _extract_and_store_memories(self, date: str, result: dict, user_context: list) -> None:
        """Store important scheduling decisions as memories."""
        # Store what was planned
        tasks_today = result.get("tasks_today", [])
        if tasks_today:
            self._db.add_memory(
                category="daily_plan",
                content=f"On {date}, planned to work on: {', '.join(tasks_today)}",
                importance=3,
            )

        # Store user context as memories
        for ctx in user_context:
            msg = ctx.get("message", "") if isinstance(ctx, dict) else str(ctx)
            if msg:
                self._db.add_memory(
                    category="user_input",
                    content=f"On {date}, user said: {msg}",
                    importance=5,
                )

        # Store deferred tasks
        tasks_later = result.get("tasks_later", [])
        if tasks_later:
            self._db.add_memory(
                category="deferred",
                content=f"On {date}, deferred: {', '.join(tasks_later)}",
                importance=4,
            )

    def parse_response(self, raw_text: str) -> dict | None:
        """Parse and validate Claude's JSON response."""
        try:
            # Strip markdown code fences if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None
        if "schedule" not in data:
            return None
        if not isinstance(data["schedule"], list):
            return None

        # Ensure required keys with defaults
        data.setdefault("tasks_today", [])
        data.setdefault("tasks_later", [])
        data.setdefault("reminders", [])

        return data

    def has_overlaps(self, schedule: list[dict]) -> bool:
        """Check if any schedule blocks overlap."""
        sorted_blocks = sorted(schedule, key=lambda b: b.get("start", ""))
        for i in range(1, len(sorted_blocks)):
            prev_end = sorted_blocks[i - 1].get("end", "")
            curr_start = sorted_blocks[i].get("start", "")
            if prev_end > curr_start:
                return True
        return False

    def store_schedule(self, date: str, result: dict) -> None:
        """Store schedule blocks in the DB, preserving completed blocks."""
        self._db.clear_schedule_blocks(date, preserve_completed=True)

        # Build a name->id lookup for pending tasks to link blocks to tasks
        pending_tasks = self._db.get_tasks(status="pending")
        task_name_map = {t["title"].lower(): t["id"] for t in pending_tasks}

        for block in result.get("schedule", []):
            # Try to match block's task name to a DB task
            task_name = block.get("task", "")
            task_id = task_name_map.get(task_name.lower()) if task_name else None

            self._db.add_schedule_block(
                date=date,
                start_time=block.get("start", ""),
                end_time=block.get("end", ""),
                block_type=block.get("type", "buffer"),
                task_id=task_id,
                ai_reason=block.get("reason"),
            )
