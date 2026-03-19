import json
import urllib.request

import pytest

from src.core.extension_server import ExtensionServer


@pytest.fixture
def server():
    srv = ExtensionServer(port=0)
    srv.start()
    yield srv
    srv.stop()


class TestUsageEndpoint:
    def test_usage_returns_json(self, server):
        port = server.get_port()
        url = f"http://127.0.0.1:{port}/usage"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            assert "today" in data
            assert "apps" in data["today"]
            assert "websites" in data["today"]
