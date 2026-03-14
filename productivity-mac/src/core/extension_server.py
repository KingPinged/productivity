"""
Local HTTP server for browser extension communication (macOS).
Allows the browser extension to sync with the desktop app's blocking state.

The server runs in a SUBPROCESS to avoid a fatal Python 3.13 GIL crash
(PyEval_RestoreThread) that occurs when any blocking I/O runs on a daemon
thread while Tkinter's mainloop occupies the main thread on macOS.

Architecture:
  Main process  <-->  shared state file  <-->  Server subprocess
  Main process  <--   event queue file   <--  Server subprocess
"""

import json
import subprocess
import sys
import atexit
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Set, Callable
import socket
from pathlib import Path


# Default port for the extension server
DEFAULT_PORT = 52525
BACKUP_PORTS = [52526, 52527, 52528, 52529]

# Shared files for cross-process communication
_APP_DATA_DIR = Path.home() / "Library" / "Application Support" / "ProductivityTimer"
_STATE_FILE = _APP_DATA_DIR / "extension_state.json"
_EVENTS_FILE = _APP_DATA_DIR / "extension_events.json"


# ── Server-side (runs in subprocess) ────────────────────────────────

def _read_shared_state() -> dict:
    """Read shared state written by the main process."""
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _append_event(event: dict) -> None:
    """Append an event for the main process to pick up."""
    try:
        events = []
        if _EVENTS_FILE.exists():
            try:
                events = json.loads(_EVENTS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                events = []
        events.append(event)
        _EVENTS_FILE.write_text(json.dumps(events))
    except OSError:
        pass


class _SubprocessHandler(BaseHTTPRequestHandler):
    """HTTP handler that reads state from shared file and posts events."""

    def log_message(self, format, *args):
        pass

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json_response(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        state = _read_shared_state()
        if self.path == '/status':
            self._json_response({
                'isBlocking': state.get('is_blocking', False),
                'blockCount': state.get('block_count', 0),
                'sitesCount': len(state.get('blocked_sites', [])),
                'appRunning': True,
            })
        elif self.path == '/sites':
            self._json_response({
                'sites': state.get('blocked_sites', []),
                'alwaysBlocked': state.get('always_blocked_sites', []),
                'whitelist': state.get('whitelisted_urls', []),
            })
        elif self.path == '/whitelist':
            self._json_response({
                'whitelist': state.get('whitelisted_urls', []),
            })
        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'pong')
        elif self.path == '/punishment-status':
            self._json_response(state.get('punishment_state', {
                'strikes_remaining': 3,
                'is_locked': False,
                'lock_time_remaining': 0,
            }))
        elif self.path == '/nsfw-cache':
            self._json_response({
                'checked_domains': state.get('nsfw_checked_domains', []),
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/adult-strike':
            _append_event({'type': 'adult_strike'})
            # Return current punishment state from shared state
            state = _read_shared_state()
            self._json_response(state.get('punishment_state', {
                'strikes_remaining': 3,
                'is_locked': False,
                'lock_time_remaining': 0,
            }))
        elif self.path == '/usage/website':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode())
                domain = data.get('domain', '')
                seconds = data.get('seconds', 0)
                if domain and seconds > 0:
                    _append_event({
                        'type': 'usage',
                        'domain': domain,
                        'seconds': seconds,
                    })
                self._json_response({'success': True})
            except Exception as e:
                self._json_response({'error': str(e)}, 400)
        elif self.path == '/check-content':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode())
                # Post event for main process to handle
                _append_event({'type': 'nsfw_check', 'signals': data})
                # Return a pending result — the extension will get the
                # real result from /nsfw-cache on next sync
                self._json_response({
                    'is_nsfw': False,
                    'confidence': 0.0,
                    'cached': False,
                    'method': 'pending',
                })
            except Exception as e:
                self._json_response({
                    'is_nsfw': False,
                    'confidence': 0.0,
                    'cached': False,
                    'method': 'error',
                })
        else:
            self.send_response(404)
            self.end_headers()


def _run_server_subprocess(port: int) -> None:
    """Entry point for the server subprocess."""
    import resource
    import signal as sig
    # Suppress crash reporter
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        sig.signal(sig.SIGABRT, sig.SIG_IGN)
    except Exception:
        pass

    ports_to_try = [port] + BACKUP_PORTS
    server = None

    for p in ports_to_try:
        try:
            server = HTTPServer(('127.0.0.1', p), _SubprocessHandler)
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = p
            break
        except socket.error:
            # Try to kill stale process
            try:
                result = subprocess.run(['lsof', '-ti', f':{p}'],
                                        capture_output=True, text=True)
                my_pid = os.getpid()
                for line in result.stdout.strip().splitlines():
                    try:
                        pid = int(line.strip())
                        if pid != my_pid:
                            subprocess.run(['kill', '-9', str(pid)],
                                           capture_output=True)
                    except ValueError:
                        pass
                time.sleep(0.3)
                server = HTTPServer(('127.0.0.1', p), _SubprocessHandler)
                server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                port = p
                break
            except (socket.error, Exception):
                continue

    if server is None:
        print("[ExtServer] Could not bind to any port")
        return

    # Write the port we bound to so the main process knows
    port_file = _APP_DATA_DIR / "extension_port"
    port_file.write_text(str(port))

    print(f"[ExtServer] Listening on http://127.0.0.1:{port}")
    server.serve_forever()


# ── Main-process side (no blocking I/O) ────────────────────────────

class ExtensionServer:
    """
    Manages the extension HTTP server subprocess and polls for events.

    The HTTP server runs in a separate process to avoid Python 3.13 GIL
    crashes.  State is shared via a JSON file; events flow back via another.
    """

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._proc: Optional[subprocess.Popen] = None
        self._running = False

        # Callbacks (called from the Tkinter main thread via root.after)
        self._adult_strike_callback: Optional[Callable[[], dict]] = None
        self._punishment_state_callback: Optional[Callable[[], dict]] = None
        self._usage_callback: Optional[Callable[[str, str, int], None]] = None
        self._nsfw_check_callback: Optional[Callable[[dict], dict]] = None
        self._nsfw_cache_callback: Optional[Callable[[], list]] = None

        # Cached state to write to shared file
        self._state = {
            'is_blocking': False,
            'blocked_sites': [],
            'always_blocked_sites': [],
            'whitelisted_urls': [],
            'block_count': 0,
            'punishment_state': {
                'strikes_remaining': 3,
                'is_locked': False,
                'lock_time_remaining': 0,
            },
            'nsfw_checked_domains': [],
        }
        self._state_dirty = True
        self._last_extension_ping: float = 0.0

    def start(self) -> bool:
        if self._running:
            return True

        _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Clear stale events
        try:
            _EVENTS_FILE.unlink(missing_ok=True)
        except OSError:
            pass

        # Write initial state
        self._flush_state()

        # Launch server subprocess
        server_module = Path(__file__).resolve()
        try:
            self._proc = subprocess.Popen(
                [sys.executable, str(server_module), "--port", str(self.port)],
                start_new_session=True,
            )
        except Exception as e:
            print(f"Failed to start extension server subprocess: {e}")
            return False

        self._running = True
        self._tk_root = None  # Set via set_tk_root() for main-thread polling

        atexit.register(self.stop)

        # Read actual port from subprocess
        time.sleep(0.5)
        try:
            port_file = _APP_DATA_DIR / "extension_port"
            if port_file.exists():
                self.port = int(port_file.read_text().strip())
        except Exception:
            pass

        print(f"Extension server running on http://127.0.0.1:{self.port}")
        return True

    def set_tk_root(self, root) -> None:
        """Set the Tkinter root and start polling on the main thread.

        This MUST be called after Tk is initialised.  All polling runs
        via root.after() on the main thread — no daemon threads — which
        avoids the Python 3.13 GIL crash entirely.
        """
        self._tk_root = root
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        """Schedule the next poll cycle on the Tkinter main thread."""
        if self._running and self._tk_root:
            self._tk_root.after(500, self._poll_tick)

    def _poll_tick(self) -> None:
        """Single poll iteration, runs on the Tkinter main thread."""
        if not self._running:
            return

        # Flush state if dirty
        if self._state_dirty:
            self._flush_state()

        # Update dynamic state (punishment, nsfw cache)
        self._refresh_dynamic_state()

        # Read and process events
        try:
            if _EVENTS_FILE.exists():
                raw = _EVENTS_FILE.read_text()
                if raw.strip():
                    events = json.loads(raw)
                    if events:
                        _EVENTS_FILE.write_text("[]")
                        for event in events:
                            try:
                                self._handle_event(event)
                            except Exception as e:
                                print(f"[ExtServer] Error handling event: {e}")
        except (json.JSONDecodeError, OSError):
            pass

        # Schedule next tick
        self._schedule_poll()

    def _flush_state(self) -> None:
        """Write current state to shared file."""
        try:
            _STATE_FILE.write_text(json.dumps(self._state))
            self._state_dirty = False
        except OSError:
            pass

    def _refresh_dynamic_state(self) -> None:
        """Refresh state that changes independently (punishment status, NSFW cache)."""
        changed = False

        if self._punishment_state_callback:
            try:
                ps = self._punishment_state_callback()
                if ps != self._state.get('punishment_state'):
                    self._state['punishment_state'] = ps
                    changed = True
            except Exception:
                pass

        if self._nsfw_cache_callback:
            try:
                domains = self._nsfw_cache_callback()
                if domains != self._state.get('nsfw_checked_domains'):
                    self._state['nsfw_checked_domains'] = domains
                    changed = True
            except Exception:
                pass

        if changed:
            self._state_dirty = True

    def _handle_event(self, event: dict) -> None:
        """Process a single event from the server subprocess."""
        etype = event.get('type')

        if etype == 'adult_strike':
            if self._adult_strike_callback:
                result = self._adult_strike_callback()
                # Update punishment state immediately
                self._state['punishment_state'] = result
                self._state_dirty = True

        elif etype == 'usage':
            domain = event.get('domain', '')
            seconds = event.get('seconds', 0)
            if self._usage_callback and domain and seconds > 0:
                print(f"[EXTENSION] Website usage received: {domain} - {seconds}s")
                self._usage_callback('website', domain, seconds)
                print(f"[EXTENSION] Usage recorded successfully")

        elif etype == 'nsfw_check':
            signals = event.get('signals', {})
            if self._nsfw_check_callback and signals:
                result = self._nsfw_check_callback(signals)
                print(f"[NSFW] Check result for {signals.get('domain', '?')}: {result}")

    def stop(self) -> None:
        """Stop the server subprocess."""
        self._running = False
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        # Clean up shared files
        try:
            _STATE_FILE.unlink(missing_ok=True)
            _EVENTS_FILE.unlink(missing_ok=True)
            (_APP_DATA_DIR / "extension_port").unlink(missing_ok=True)
        except OSError:
            pass

    # ── State setters (called from main process) ──

    def set_blocking_state(self, is_blocking: bool):
        self._state['is_blocking'] = is_blocking
        self._state_dirty = True

    def set_blocked_sites(self, sites: Set[str]):
        self._state['blocked_sites'] = list(sites)
        self._state_dirty = True

    def set_always_blocked_sites(self, sites: Set[str]):
        self._state['always_blocked_sites'] = list(sites)
        self._state_dirty = True

    def set_whitelisted_urls(self, urls: list):
        self._state['whitelisted_urls'] = urls
        self._state_dirty = True

    def increment_block_count(self):
        self._state['block_count'] = self._state.get('block_count', 0) + 1
        self._state_dirty = True

    def reset_block_count(self):
        self._state['block_count'] = 0
        self._state_dirty = True

    # ── Callback setters ──

    def set_adult_strike_callback(self, callback: Callable[[], dict]):
        self._adult_strike_callback = callback

    def set_punishment_state_callback(self, callback: Callable[[], dict]):
        self._punishment_state_callback = callback

    def set_usage_callback(self, callback: Callable[[str, str, int], None]):
        self._usage_callback = callback

    def set_nsfw_check_callback(self, callback: Callable[[dict], dict]):
        self._nsfw_check_callback = callback

    def set_nsfw_cache_callback(self, callback: Callable[[], list]):
        self._nsfw_cache_callback = callback

    # ── State accessors ──

    def get_blocked_sites(self) -> Set[str]:
        return set(self._state.get('blocked_sites', []))

    def get_always_blocked_sites(self) -> Set[str]:
        return set(self._state.get('always_blocked_sites', []))

    def add_always_blocked_site(self, domain: str) -> None:
        sites = self._state.get('always_blocked_sites', [])
        if domain not in sites:
            sites.append(domain)
            self._state['always_blocked_sites'] = sites
            self._state_dirty = True

    def update_always_blocked_sites(self, domains) -> None:
        """Add multiple domains to always-blocked list."""
        sites = set(self._state.get('always_blocked_sites', []))
        sites.update(domains)
        self._state['always_blocked_sites'] = list(sites)
        self._state_dirty = True

    # ── Queries ──

    def is_extension_connected(self, timeout: float = 10.0) -> bool:
        """Check if the server subprocess is alive (proxy for extension connectivity)."""
        if self._proc is None:
            return False
        return self._proc.poll() is None

    def get_port(self) -> int:
        return self.port


# ── Subprocess entry point ──────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    _run_server_subprocess(args.port)
