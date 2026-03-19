import logging
import platform
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent / "assets"

SOUND_MAP = {
    "event": "chime.wav",
    "task_start": "tone.wav",
    "deadline": "urgent.wav",
    "break": "bell.wav",
    "nudge": "ping.wav",
    "summary": None,  # No sound for daily summary
}


class Notifier:
    """Cross-platform notification + sound dispatcher."""

    def send(self, title: str, message: str, reminder_type: str = "event") -> None:
        """Send a system notification with optional sound."""
        # Fire sound in background thread (non-blocking)
        sound_file = SOUND_MAP.get(reminder_type)
        if sound_file:
            threading.Thread(
                target=self._play_sound,
                args=(sound_file,),
                daemon=True,
            ).start()

        # Send system notification
        try:
            self._send_notification(title, message)
        except Exception as e:
            logger.warning("Failed to send notification: %s", e)

    def _send_notification(self, title: str, message: str) -> None:
        """Send a native system notification."""
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name="Productivity Planner",
                timeout=10,
            )
        except Exception as e:
            logger.warning("plyer notification failed: %s", e)
            # Fallback: try platform-specific
            if platform.system() == "Windows":
                self._windows_fallback(title, message)

    def _play_sound(self, filename: str) -> None:
        """Play a .wav sound file."""
        sound_path = ASSETS_DIR / filename
        if not sound_path.exists():
            return

        try:
            if platform.system() == "Windows":
                import winsound
                winsound.PlaySound(str(sound_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                # macOS / Linux fallback
                import subprocess
                if platform.system() == "Darwin":
                    subprocess.Popen(["afplay", str(sound_path)])
                else:
                    subprocess.Popen(["aplay", "-q", str(sound_path)])
        except Exception as e:
            logger.warning("Failed to play sound %s: %s", filename, e)

    def _windows_fallback(self, title: str, message: str) -> None:
        """Windows fallback using win10toast or ctypes."""
        try:
            import ctypes
            ctypes.windll.user32.MessageBeep(0)
        except Exception:
            pass
