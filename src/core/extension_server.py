"""
Local HTTP server for browser extension communication.
Allows the browser extension to sync with the desktop app's blocking state.
"""

import json
import threading
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
    whitelisted_urls: list = []
    block_count: int = 0

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def _send_cors_headers(self):
        """Send CORS headers to allow extension access."""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
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
        """Return list of blocked sites and whitelisted URLs."""
        response = {
            'sites': list(ExtensionRequestHandler.blocked_sites),
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
                self._server = HTTPServer(('127.0.0.1', port), ExtensionRequestHandler)
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

        print(f"Extension server running on http://127.0.0.1:{self.port}")
        return True

    def _run(self):
        """Server thread main loop."""
        while self._running:
            self._server.handle_request()

    def stop(self):
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server = None

    def set_blocking_state(self, is_blocking: bool):
        """Update the blocking state."""
        ExtensionRequestHandler.is_blocking = is_blocking

    def set_blocked_sites(self, sites: Set[str]):
        """Update the list of blocked sites."""
        ExtensionRequestHandler.blocked_sites = sites

    def set_whitelisted_urls(self, urls: list):
        """Update the list of whitelisted URLs."""
        ExtensionRequestHandler.whitelisted_urls = urls

    def increment_block_count(self):
        """Increment the block counter."""
        ExtensionRequestHandler.block_count += 1

    def reset_block_count(self):
        """Reset the block counter."""
        ExtensionRequestHandler.block_count = 0

    def get_port(self) -> int:
        """Get the port the server is running on."""
        return self.port
