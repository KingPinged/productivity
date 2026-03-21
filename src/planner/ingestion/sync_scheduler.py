import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager
from src.planner.ingestion.gcal import GCalSyncer
from src.planner.ingestion.gmail import GmailSyncer
from src.planner.ingestion.canvas_requests import CanvasRequestsScraper
from src.planner.encryption import EncryptionManager

logger = logging.getLogger(__name__)

class SyncScheduler:
    def __init__(self, db: PlannerDB, auth_manager: GoogleAuthManager | None = None, encryption: EncryptionManager | None = None):
        self._db = db
        self._auth_manager = auth_manager
        self._gcal_syncer = GCalSyncer(db)
        self._gmail_syncer = GmailSyncer(db)
        self._canvas_scraper = CanvasRequestsScraper(db, encryption) if encryption else None
        self._scheduler = BackgroundScheduler()
        self._lock = threading.Lock()
        self._ai_scheduler = None  # Set by server.py after creation

    def set_ai_scheduler(self, ai_scheduler):
        """Set the AI scheduler for auto-replanning after syncs."""
        self._ai_scheduler = ai_scheduler

    def start(self, google_interval_minutes: int = 15, canvas_interval_minutes: int = 120) -> None:
        # Google sync every 15 min
        self._scheduler.add_job(
            self.sync_all, "interval", minutes=google_interval_minutes,
            id="sync_google", replace_existing=True,
        )
        # Canvas sync every 2 hours
        if self._canvas_scraper:
            self._scheduler.add_job(
                self.sync_canvas, "interval", minutes=canvas_interval_minutes,
                id="sync_canvas", replace_existing=True,
            )
        # Morning schedule generation — every day at wake time
        wake_time = self._db.get_preference("wake_time", "07:00")
        try:
            hour, minute = (int(x) for x in wake_time.split(":"))
        except Exception:
            hour, minute = 7, 0

        self._scheduler.add_job(
            self._morning_generate,
            "cron",
            hour=hour, minute=minute,
            timezone="America/Chicago",
            id="morning_generate",
            replace_existing=True,
        )
        logger.info("Morning schedule generation set for %s CT", wake_time)

        self._scheduler.start()

    def trigger_startup_generate(self):
        """Call after AI scheduler is set to generate initial schedules."""
        if self._ai_scheduler:
            self._scheduler.add_job(
                self._morning_generate,
                "date",  # Run once, now
                id="startup_generate",
                replace_existing=True,
            )

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def _morning_generate(self):
        """Generate a full week of schedule blocks."""
        if not self._ai_scheduler:
            logger.warning("AI scheduler not available, skipping morning generation")
            return
        logger.info("Running morning schedule generation (7 days)")
        try:
            results = self._ai_scheduler.generate_week()
            total = sum(v for v in results.values() if v > 0)
            logger.info("Morning generation complete: %d total blocks across %d days", total, len(results))
        except Exception as e:
            logger.error("Morning generation failed: %s", e)

    def _smart_replan(self):
        """Trigger a smart replan (today + tomorrow) after data changes."""
        if not self._ai_scheduler:
            return
        try:
            results = self._ai_scheduler.smart_replan()
            if results:
                logger.info("Smart replan: %s", results)
        except Exception as e:
            logger.error("Smart replan failed: %s", e)

    def sync_all(self) -> dict[str, int]:
        if not self._auth_manager:
            return {}
        with self._lock:
            results = {}
            accounts = self._db.list_accounts()
            data_changed = False
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
                    if cal_count + gmail_count > 0:
                        data_changed = True
                    logger.info("Synced %s: %d cal + %d gmail events", email, cal_count, gmail_count)
                except Exception as e:
                    logger.error("Failed to sync %s: %s", email, e)
                    results[email] = -1

            # Auto-replan if new data came in
            if data_changed:
                logger.info("Data changed after sync, triggering smart replan")
                threading.Thread(target=self._smart_replan, daemon=True).start()

            return results

    def sync_canvas(self) -> dict[str, int]:
        """Sync all Canvas configs. Returns dict of url -> task count."""
        if not self._canvas_scraper:
            return {}
        with self._lock:
            results = {}
            data_changed = False
            configs = self._db.list_canvas_configs()
            for config in configs:
                if config["status"] != "active":
                    continue
                try:
                    count = self._canvas_scraper.sync_config(config["id"])
                    results[config["canvas_url"]] = count
                    if count > 0:
                        data_changed = True
                    logger.info("Canvas sync %s: %d tasks", config["canvas_url"], count)
                except Exception as e:
                    logger.error("Canvas sync failed for %s: %s", config["canvas_url"], e)
                    results[config["canvas_url"]] = -1

            # Auto-replan if new data came in
            if data_changed:
                logger.info("Canvas data changed, triggering smart replan")
                threading.Thread(target=self._smart_replan, daemon=True).start()

            return results
