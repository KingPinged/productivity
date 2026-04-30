"""
Process guard - monitors and respawns the app if killed (macOS).
Runs as a separate process to make the app harder to terminate.

Dual-guard system: two guard processes watch both the main app and
each other, so killing one guard still leaves another to respawn it.

Modes:
  - Legacy mode: guard.watch() spawns and watches the main app
  - PID watch mode: --watch-pid <PID> monitors an existing process
    and respawns run.py if it dies (unless clean_exit sentinel exists)
"""

import argparse
import json
import signal
import subprocess
import sys
import os
import time
import psutil
import threading
from pathlib import Path

# State directory mirrors src.utils.constants.APP_DATA_DIR but is
# duplicated here so this module works when launched as a subprocess
# before sys.path is patched.
_GUARD_STATE_DIR = Path.home() / "Library" / "Application Support" / "ProductivityTimer"


def is_process_running(process_name: str) -> bool:
    """Check if a process with given name is running."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def get_process_by_name(process_name: str) -> psutil.Process:
    """Get process by name."""
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            if proc.info['name'] and process_name.lower() in proc.info['name'].lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def set_process_priority_low():
    """Set this process to low priority to stay unobtrusive."""
    try:
        os.nice(19)
    except Exception:
        pass


def count_running_guards(exclude_pid: int = None) -> int:
    """Count how many guard processes are currently running."""
    count = 0
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.info['pid'] == exclude_pid:
                continue
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(cmdline)
            if '--watch-pid' in cmdline_str and 'process_guard' in cmdline_str:
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count


def is_guard_already_running(exclude_pid: int = None) -> bool:
    """Check if another guard process is already running."""
    return count_running_guards(exclude_pid) > 0


# ── Guard state files ──────────────────────────────────────────────
#
# Each guard records (guard_pid, watched_pid, guard_id) in
# guard-{id}.state.json so we can verify which app instance a guard
# is actually watching.  cmdline alone lies after adoption — the
# argv stays frozen even though the watched pid has changed.

def _guard_state_path(guard_id: int) -> Path:
    return _GUARD_STATE_DIR / f"guard-{guard_id}.state.json"


def _write_guard_state(guard_id: int, watched_pid: int) -> None:
    """Persist this guard's watched pid so other processes can see it."""
    try:
        _GUARD_STATE_DIR.mkdir(parents=True, exist_ok=True)
        _guard_state_path(guard_id).write_text(json.dumps({
            "guard_pid": os.getpid(),
            "watched_pid": int(watched_pid),
            "guard_id": int(guard_id),
            "updated_at": time.time(),
        }))
    except OSError as e:
        print(f"[Guard-{guard_id}] Failed to write state file: {e}")


def _enumerate_guards() -> list:
    """Return one dict per alive guard process.

    Prefer state-file data (post-fix guards).  Fall back to parsing
    cmdline for legacy guards launched before this change.  Stale
    state files (dead guard pid) are removed as a side effect.
    """
    seen_pids: set[int] = set()
    out: list[dict] = []

    if _GUARD_STATE_DIR.exists():
        for f in _GUARD_STATE_DIR.glob("guard-*.state.json"):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            gpid = data.get("guard_pid")
            if not isinstance(gpid, int) or not psutil.pid_exists(gpid):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            seen_pids.add(gpid)
            out.append({
                "guard_pid": gpid,
                "watched_pid": data.get("watched_pid"),
                "guard_id": data.get("guard_id"),
                "source": "state",
            })

    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            pid = proc.info['pid']
            if pid in seen_pids:
                continue
            cmdline = proc.info.get('cmdline') or []
            if 'process_guard' not in ' '.join(cmdline) or '--watch-pid' not in cmdline:
                continue
            try:
                idx = cmdline.index('--watch-pid')
                wpid = int(cmdline[idx + 1])
            except (ValueError, IndexError):
                continue
            gid = None
            if '--guard-id' in cmdline:
                try:
                    gid = int(cmdline[cmdline.index('--guard-id') + 1])
                except (ValueError, IndexError):
                    pass
            out.append({
                "guard_pid": pid,
                "watched_pid": wpid,
                "guard_id": gid,
                "source": "cmdline",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    return out


def count_guards_watching_pid(target_pid: int, exclude_pid: int = None) -> int:
    """Number of alive guards whose watched_pid equals target_pid."""
    return sum(
        1
        for g in _enumerate_guards()
        if g.get("watched_pid") == target_pid
        and (exclude_pid is None or g.get("guard_pid") != exclude_pid)
    )


def kill_orphaned_guards(current_app_pid: int) -> int:
    """Kill guards whose watched pid is dead and != current_app_pid.

    Leaves guards alone if they're watching a different live process
    (could be a second app instance — not our problem to terminate).
    """
    killed = 0
    for g in _enumerate_guards():
        gpid = g.get("guard_pid")
        wpid = g.get("watched_pid")
        if wpid == current_app_pid:
            continue
        if isinstance(wpid, int) and psutil.pid_exists(wpid):
            continue  # watching some other live app — leave alone
        try:
            os.kill(gpid, signal.SIGTERM)
            print(f"[Guard cleanup] Killed orphaned guard PID {gpid} "
                  f"(was watching dead PID {wpid})")
            killed += 1
        except (ProcessLookupError, PermissionError) as e:
            print(f"[Guard cleanup] Could not kill PID {gpid}: {e}")
        # Drop state file for the now-dead guard
        gid = g.get("guard_id")
        if isinstance(gid, int):
            try:
                _guard_state_path(gid).unlink(missing_ok=True)
            except OSError:
                pass
    return killed


class ProcessGuard:
    """
    Watches the main app and respawns it if killed.
    """

    def __init__(self, main_app_path: str, check_interval: int = 3):
        """
        Initialize the process guard.

        Args:
            main_app_path: Path to the main app executable/script
            check_interval: Seconds between checks
        """
        self.main_app_path = Path(main_app_path)
        self.check_interval = check_interval
        self._running = False
        self._main_process = None

    def start_main_app(self) -> bool:
        """Start the main application."""
        try:
            if self.main_app_path.suffix == '.py':
                # Running as Python script
                self._main_process = subprocess.Popen(
                    [sys.executable, str(self.main_app_path)]
                )
            elif self.main_app_path.suffix == '.app':
                # Running as macOS .app bundle
                self._main_process = subprocess.Popen(
                    ['open', '-a', str(self.main_app_path)]
                )
            else:
                # Running as compiled binary
                self._main_process = subprocess.Popen(
                    [str(self.main_app_path)]
                )
            return True
        except Exception as e:
            print(f"Failed to start main app: {e}")
            return False

    def is_main_app_running(self) -> bool:
        """Check if main app is still running."""
        if self._main_process is None:
            return False

        return self._main_process.poll() is None

    def watch(self):
        """Main watch loop - respawns app if killed."""
        import signal

        self._running = True
        set_process_priority_low()

        # Handle SIGTERM/SIGINT so guard exits during system shutdown
        def _stop(signum, frame):
            print(f"[Guard] Signal {signum} received — exiting")
            self._running = False

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        # Initial launch
        self.start_main_app()
        time.sleep(2)  # Give it time to start

        while self._running:
            try:
                if not self.is_main_app_running():
                    print("Main app terminated. Respawning...")
                    time.sleep(1)
                    self.start_main_app()

                time.sleep(self.check_interval)

            except Exception as e:
                print(f"Guard error: {e}")
                time.sleep(self.check_interval)

    def stop(self):
        """Stop the guard."""
        self._running = False


def find_main_app() -> Path:
    """Find the main app executable or script."""
    if getattr(sys, 'frozen', False):
        # Running as compiled binary
        exe_dir = Path(sys.executable).parent
        # Look for the main app
        for name in ["ProductivityTimer", "main"]:
            candidate = exe_dir / name
            if candidate.exists():
                return candidate
        # Fall back to any binary that's not us
        for f in exe_dir.iterdir():
            if f.is_file() and f.name != Path(sys.executable).name and not f.suffix:
                return f
    else:
        # Running as Python script
        script_dir = Path(__file__).parent.parent.parent
        return script_dir / "run.py"

    return None


def _find_running_app(exclude_pid: int = None) -> int:
    """Find a running instance of the main app and return its PID, or None."""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.info['pid'] == exclude_pid:
                continue
            cmdline = proc.info.get('cmdline') or []
            cmdline_str = ' '.join(cmdline)
            # Match the main app (run.py / main.py) but not guard processes
            if ('run.py' in cmdline_str or 'src.main' in cmdline_str) \
                    and '--watch-pid' not in cmdline_str:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def _spawn_peer_guard(guard_script: str, app_pid: int, guard_id: int) -> int:
    """Spawn a peer guard process and return its PID."""
    try:
        proc = subprocess.Popen(
            [sys.executable, guard_script,
             "--watch-pid", str(app_pid),
             "--guard-id", str(guard_id)],
            start_new_session=True,
        )
        print(f"[Guard] Respawned peer guard {guard_id} with PID {proc.pid}")
        return proc.pid
    except Exception as e:
        print(f"[Guard] Failed to respawn peer guard: {e}")
        return None


def _restore_dns_if_needed() -> None:
    """Restore DNS settings if a saved original config exists.

    Called when the main app crashes to prevent DNS lockout.
    """
    try:
        from src.core.dns_proxy import restore_dns_settings, _DNS_ORIGINAL_FILE
        if _DNS_ORIGINAL_FILE.exists():
            print("[Guard] Restoring DNS settings after app crash")
            restore_dns_settings()
    except Exception as e:
        print(f"[Guard] DNS restore failed: {e}")


def watch_pid(pid: int, guard_id: int = 1, check_interval: int = 3) -> None:
    """
    Monitor the main app PID and respawn run.py if it dies,
    unless the clean_exit sentinel file exists.
    Also monitors peer guard and respawns it if killed.
    """
    import signal
    from src.utils.constants import CLEAN_EXIT_FILE

    # Handle SIGTERM/SIGINT so guards exit during system shutdown
    # instead of racing to respawn the app.
    _guard_running = True

    def _handle_shutdown_signal(signum, frame):
        nonlocal _guard_running
        print(f"[Guard-{guard_id}] Signal {signum} received — exiting")
        _guard_running = False

    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    set_process_priority_low()
    main_app = find_main_app()
    guard_script = str(Path(__file__).resolve())
    peer_id = 2 if guard_id == 1 else 1

    if main_app is None:
        print(f"[Guard-{guard_id}] Could not find main application!")
        return

    print(f"[Guard-{guard_id}] Watching app PID {pid}, will respawn if killed")
    _write_guard_state(guard_id, pid)

    try:
        while _guard_running:
            time.sleep(check_interval)

            # --- Check clean exit (both guards should stop) ---
            # NOTE: Don't delete the sentinel here — the app deletes it on
            # startup.  If we deleted it, the peer guard might miss it and
            # respawn the app.
            if CLEAN_EXIT_FILE.exists():
                print(f"[Guard-{guard_id}] Clean exit detected — stopping guard")
                # Ensure DNS is restored on clean exit too
                _restore_dns_if_needed()
                return

            # --- Check peer guard health ---
            peer_count = count_running_guards(exclude_pid=os.getpid())
            if peer_count == 0:
                print(f"[Guard-{guard_id}] Peer guard missing — respawning guard-{peer_id}")
                _spawn_peer_guard(guard_script, pid, peer_id)

            # --- Check main app health ---
            if psutil.pid_exists(pid):
                continue

            # PID is gone — stagger by guard_id so only one guard respawns
            time.sleep(guard_id)

            # Re-check: signal received during stagger sleep means system shutdown
            if not _guard_running:
                print(f"[Guard-{guard_id}] Signal received during respawn check — exiting")
                return

            # Re-check: clean exit, or maybe peer already respawned
            if CLEAN_EXIT_FILE.exists():
                print(f"[Guard-{guard_id}] Clean exit detected — stopping guard")
                return

            # Check if peer guard already respawned the app
            existing_pid = _find_running_app()
            if existing_pid is not None:
                print(f"[Guard-{guard_id}] App already running (PID {existing_pid}) — adopting")
                pid = existing_pid
                _write_guard_state(guard_id, pid)
                continue

            # Force-killed — restore DNS before respawning
            _restore_dns_if_needed()

            print(f"[Guard-{guard_id}] App PID {pid} died unexpectedly — respawning {main_app}")

            try:
                if main_app.suffix == '.py':
                    proc = subprocess.Popen([sys.executable, str(main_app)])
                else:
                    proc = subprocess.Popen([str(main_app)])

                # Now watch the new process
                pid = proc.pid
                _write_guard_state(guard_id, pid)
                print(f"[Guard-{guard_id}] New app started with PID {pid}")
            except Exception as e:
                print(f"[Guard-{guard_id}] Failed to respawn: {e}")
                time.sleep(5)
    finally:
        try:
            _guard_state_path(guard_id).unlink(missing_ok=True)
        except OSError:
            pass


def run_guard():
    """Entry point for running as guard process."""
    main_app = find_main_app()

    if main_app is None:
        print("Could not find main application!")
        return

    print(f"Guard starting. Watching: {main_app}")
    guard = ProcessGuard(str(main_app))
    guard.watch()


if __name__ == "__main__":
    # Suppress macOS crash reporter dialog
    import resource
    import signal
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        signal.signal(signal.SIGABRT, signal.SIG_IGN)
    except Exception:
        pass

    # Add project root to path so `from src.…` imports work when
    # this file is launched as a standalone subprocess.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    parser = argparse.ArgumentParser()
    parser.add_argument('--watch-pid', type=int, help='PID to monitor')
    parser.add_argument('--guard-id', type=int, default=1, help='Guard instance ID (1 or 2)')
    parser.add_argument('--status', action='store_true',
                        help='Print all alive guards and exit')
    args = parser.parse_args()

    if args.status:
        rows = _enumerate_guards()
        if not rows:
            print("No guards running")
        else:
            print(f"{'guard_pid':>10}  {'guard_id':>8}  {'watched_pid':>11}  {'watched_alive':>13}  source")
            for g in rows:
                wpid = g.get("watched_pid")
                alive = "yes" if isinstance(wpid, int) and psutil.pid_exists(wpid) else "no"
                print(f"{g['guard_pid']:>10}  "
                      f"{str(g.get('guard_id')):>8}  "
                      f"{str(wpid):>11}  "
                      f"{alive:>13}  "
                      f"{g.get('source')}")
        sys.exit(0)

    if args.watch_pid:
        watch_pid(args.watch_pid, guard_id=args.guard_id)
    else:
        run_guard()
