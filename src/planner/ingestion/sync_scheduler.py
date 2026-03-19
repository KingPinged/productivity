import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager
from src.planner.ingestion.gcal import GCalSyncer
from src.planner.ingestion.gmail import GmailSyncer

logger = logging.getLogger(__name__)

class SyncScheduler:
    def __init__(self, db: PlannerDB, auth_manager: GoogleAuthManager | None = None):
        self._db = db
        self._auth_manager = auth_manager
        self._gcal_syncer = GCalSyncer(db)
        self._gmail_syncer = GmailSyncer(db)
        self._scheduler = BackgroundScheduler()
        self._lock = threading.Lock()

    def start(self, interval_minutes: int = 15) -> None:
        self._scheduler.add_job(
            self.sync_all, "interval", minutes=interval_minutes,
            id="sync_all", replace_existing=True,
        )
        self._scheduler.start()

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def sync_all(self) -> dict[str, int]:
        if not self._auth_manager:
            return {}
        with self._lock:
            results = {}
            accounts = self._db.list_accounts()
            for account in accounts:
                email = account["email"]
                try:
                    creds = self._auth_manager.refresh_if_expired(email)
                    if creds is None:
                        logger.warning("No credentials for %s, skipping", email)
                        continue
                    from googleapiclient.discovery import build
                    cal_service = build("calendar", "v3", credentials=creds)
                    cal_count = self._gcal_syncer.sync_account(account["id"], cal_service)
                    gmail_service = build("gmail", "v1", credentials=creds)
                    gmail_count = self._gmail_syncer.sync_account(account["id"], gmail_service)
                    results[email] = cal_count + gmail_count
                    logger.info("Synced %s: %d cal + %d gmail events", email, cal_count, gmail_count)
                except Exception as e:
                    logger.error("Failed to sync %s: %s", email, e)
                    results[email] = -1
            return results
