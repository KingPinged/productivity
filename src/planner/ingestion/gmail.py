import base64
from datetime import datetime, timezone

from src.planner.db import PlannerDB


class GmailSyncer:
    def __init__(self, db: PlannerDB):
        self._db = db

    def fetch_recent_messages(self, service, max_results: int = 50) -> list[dict]:
        """Fetch recent inbox and starred messages, skipping promotions/spam."""
        # Fetch from inbox (excluding promotions/social/spam)
        inbox_results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q="-category:promotions -category:social -in:spam in:inbox",
        ).execute()

        # Also fetch starred messages (may not be in inbox)
        starred_results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q="is:starred",
        ).execute()

        # Merge and dedup by message ID
        seen_ids = set()
        msg_stubs = []
        for result in [inbox_results, starred_results]:
            for stub in result.get("messages", []):
                if stub["id"] not in seen_ids:
                    seen_ids.add(stub["id"])
                    msg_stubs.append(stub)

        messages = []
        for msg_stub in msg_stubs[:max_results]:
            msg = service.users().messages().get(
                userId="me", id=msg_stub["id"], format="full"
            ).execute()
            messages.append(msg)

        return messages

    def extract_metadata(self, message: dict) -> dict:
        headers = message.get("payload", {}).get("headers", [])
        header_map = {h["name"].lower(): h["value"] for h in headers}

        body = ""
        payload = message.get("payload", {})
        if payload.get("body", {}).get("data"):
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break

        return {
            "message_id": message.get("id", ""),
            "subject": header_map.get("subject", "(No subject)"),
            "from": header_map.get("from", ""),
            "date": header_map.get("date", ""),
            "body": body,
            "snippet": message.get("snippet", ""),
            "label_ids": message.get("labelIds", []),
        }

    def store_email_event(
        self,
        account_id: int,
        message_id: str,
        subject: str,
        date_str: str,
        snippet: str = "",
    ) -> int:
        return self._db.upsert_event(
            account_id=account_id,
            source="gmail",
            external_id=f"gmail:{message_id}",
            title=subject,
            description=snippet,
            start_time=date_str,
            event_type="email",
        )

    def sync_account(self, account_id: int, service) -> int:
        """Fetch and store recent emails as raw events. Returns count stored.

        Note: In Phase 2, emails are stored as-is with subject/snippet metadata.
        Claude-based action item extraction (parsing emails for deadlines, tasks,
        and date references) is implemented in Phase 4 (AI Scheduling Engine),
        which processes these stored emails to create tasks.
        """
        messages = self.fetch_recent_messages(service)
        count = 0
        for msg in messages:
            meta = self.extract_metadata(msg)
            result = self.store_email_event(
                account_id=account_id,
                message_id=meta["message_id"],
                subject=meta["subject"],
                date_str=meta["date"],
                snippet=meta["snippet"],
            )
            if result != 0:  # 0 means no change
                count += 1

        now = datetime.now(timezone.utc).isoformat()
        self._db.update_account_last_sync(account_id, now)
        return count
