"""
Local HTTP server for browser extension communication (macOS).
Allows the browser extension to sync with the desktop app's blocking state.
"""

import json
import threading
import atexit
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Set, Callable
import socket


# Default port for the extension server
DEFAULT_PORT = 52525
BACKUP_PORTS = [52526, 52527, 52528, 52529]


class ExtensionRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for extension communication."""

    # Class-level state (shared across requests)
    is_blocking: bool = False
    blocked_sites: Set[str] = set()
    always_blocked_sites: Set[str] = set()  # Adult sites - always blocked
    whitelisted_urls: list = []
    block_count: int = 0

    # Punishment system callbacks
    adult_strike_callback: Optional[Callable[[], dict]] = None
    punishment_state_callback: Optional[Callable[[], dict]] = None

    # Usage tracking callback
    usage_callback: Optional[Callable[[str, str, int], None]] = None

    # NSFW detection callbacks
    nsfw_check_callback: Optional[Callable[[dict], dict]] = None
    nsfw_cache_callback: Optional[Callable[[], list]] = None

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def _send_cors_headers(self):
        """Send CORS headers to allow extension access."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/status':
            self._handle_status()
        elif self.path == '/sites':
            self._handle_sites()
        elif self.path == '/whitelist':
            self._handle_whitelist()
        elif self.path == '/ping':
            self._handle_ping()
        elif self.path == '/punishment-status':
            self._handle_punishment_status()
        elif self.path == '/nsfw-cache':
            self._handle_nsfw_cache()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST requests."""
        if self.path == '/adult-strike':
            self._handle_adult_strike()
        elif self.path == '/usage/website':
            self._handle_website_usage()
        elif self.path == '/check-content':
            self._handle_check_content()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_status(self):
        """Return current blocking status."""
        response = {
            'isBlocking': ExtensionRequestHandler.is_blocking,
            'blockCount': ExtensionRequestHandler.block_count,
            'sitesCount': len(ExtensionRequestHandler.blocked_sites),
            'appRunning': True
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_sites(self):
        """Return list of blocked sites, always-blocked sites, and whitelisted URLs."""
        response = {
            'sites': list(ExtensionRequestHandler.blocked_sites),
            'alwaysBlocked': list(ExtensionRequestHandler.always_blocked_sites),
            'whitelist': ExtensionRequestHandler.whitelisted_urls
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_whitelist(self):
        """Return list of whitelisted URLs."""
        response = {
            'whitelist': ExtensionRequestHandler.whitelisted_urls
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_ping(self):
        """Simple ping to check if server is running."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(b'pong')

    def _handle_punishment_status(self):
        """Return current punishment status for block page."""
        callback = ExtensionRequestHandler.punishment_state_callback

        if callback:
            response = callback()
        else:
            response = {
                'strikes_remaining': 3,
                'is_locked': False,
                'lock_time_remaining': 0
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_adult_strike(self):
        """Handle adult site visit attempt - increment strike counter."""
        callback = ExtensionRequestHandler.adult_strike_callback

        if callback:
            response = callback()
        else:
            response = {
                'strikes_remaining': 3,
                'is_locked': False,
                'lock_time_remaining': 0
            }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())

    def _handle_website_usage(self):
        """Handle website usage report from extension."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())

            domain = data.get('domain', '')
            seconds = data.get('seconds', 0)

            print(f"[EXTENSION] Website usage received: {domain} - {seconds}s")

            callback = ExtensionRequestHandler.usage_callback
            if callback and domain and seconds > 0:
                callback('website', domain, seconds)
                print(f"[EXTENSION] Usage recorded successfully")
            elif not callback:
                print("[EXTENSION] Warning: No usage callback registered!")
            elif not domain:
                print("[EXTENSION] Warning: Empty domain received")
            elif seconds <= 0:
                print(f"[EXTENSION] Warning: Invalid seconds value: {seconds}")

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"success": true}')

        except Exception as e:
            print(f"[EXTENSION] Error handling website usage: {e}")
            self.send_response(400)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(f'{{"error": "{str(e)}"}}'.encode())

    def _handle_check_content(self):
        """Handle AI NSFW content check request from extension."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode())

            callback = ExtensionRequestHandler.nsfw_check_callback
            if callback:
                result = callback(data)
            else:
                result = {'is_nsfw': False, 'confidence': 0.0, 'cached': False, 'method': 'disabled'}

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        except Exception as e:
            print(f"[EXTENSION] Error handling content check: {e}")
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            # Fail open - return safe on error
            self.wfile.write(b'{"is_nsfw": false, "confidence": 0, "cached": false, "method": "error"}')

    def _handle_nsfw_cache(self):
        """Return all cached NSFW domain classifications for extension sync."""
        callback = ExtensionRequestHandler.nsfw_cache_callback
        if callback:
            domains = callback()
        else:
            domains = []

        response = {'checked_domains': domains}

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())


class ExtensionServer:
    """
    Local HTTP server for browser extension communication.
    Runs on localhost and allows the extension to query blocking status.
    """

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _kill_stale_server(self, port: int) -> None:
        """Kill any stale process occupying our port."""
        try:
            import subprocess
            # Use lsof to find process on the port
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True, text=True,
            )
            my_pid = os.getpid()
            for line in result.stdout.strip().splitlines():
                try:
                    pid = int(line.strip())
                    if pid != my_pid and pid != 0:
                        print(f"Killing stale server process on port {port} (PID {pid})")
                        subprocess.run(
                            ['kill', '-9', str(pid)],
                            capture_output=True,
                        )
                except ValueError:
                    pass
        except Exception as e:
            print(f"Could not kill stale server: {e}")

    def start(self) -> bool:
        """
        Start the server.

        Returns:
            True if server started successfully
        """
        if self._running:
            return True

        # Try the default port first, then backups
        ports_to_try = [self.port] + BACKUP_PORTS

        for port in ports_to_try:
            try:
                server = HTTPServer(('127.0.0.1', port), ExtensionRequestHandler)
                server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._server = server
                self.port = port
                break
            except socket.error:
                # Port in use - try to kill stale process, then retry once
                self._kill_stale_server(port)
                try:
                    server = HTTPServer(('127.0.0.1', port), ExtensionRequestHandler)
                    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self._server = server
                    self.port = port
                    break
                except socket.error:
                    continue
        else:
            print("Could not start extension server - all ports in use")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

        # Register cleanup so the port is freed on exit
        atexit.register(self.stop)

        print(f"Extension server running on http://127.0.0.1:{self.port}")
        return True

    def _run(self):
        """Server thread main loop."""
        while self._running:
            self._server.handle_request()

    def stop(self):
        """Stop the server and release the port."""
        self._running = False
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def set_blocking_state(self, is_blocking: bool):
        """Update the blocking state."""
        ExtensionRequestHandler.is_blocking = is_blocking

    def set_blocked_sites(self, sites: Set[str]):
        """Update the list of blocked sites."""
        ExtensionRequestHandler.blocked_sites = sites

    def set_always_blocked_sites(self, sites: Set[str]):
        """Update the list of always-blocked sites (adult content)."""
        ExtensionRequestHandler.always_blocked_sites = sites

    def set_whitelisted_urls(self, urls: list):
        """Update the list of whitelisted URLs."""
        ExtensionRequestHandler.whitelisted_urls = urls

    def increment_block_count(self):
        """Increment the block counter."""
        ExtensionRequestHandler.block_count += 1

    def reset_block_count(self):
        """Reset the block counter."""
        ExtensionRequestHandler.block_count = 0

    def set_adult_strike_callback(self, callback: Callable[[], dict]):
        """Set callback for adult site strike events."""
        ExtensionRequestHandler.adult_strike_callback = callback

    def set_punishment_state_callback(self, callback: Callable[[], dict]):
        """Set callback to get current punishment state."""
        ExtensionRequestHandler.punishment_state_callback = callback

    def set_usage_callback(self, callback: Callable[[str, str, int], None]):
        """Set callback for usage reports: callback(category, name, seconds)."""
        ExtensionRequestHandler.usage_callback = callback

    def set_nsfw_check_callback(self, callback: Callable[[dict], dict]):
        """Set callback for NSFW content checks: callback(signals_dict) -> result_dict."""
        ExtensionRequestHandler.nsfw_check_callback = callback

    def set_nsfw_cache_callback(self, callback: Callable[[], list]):
        """Set callback to get all checked domains: callback() -> list of domain strings."""
        ExtensionRequestHandler.nsfw_cache_callback = callback

    def get_port(self) -> int:
        """Get the port the server is running on."""
        return self.port
