import httpx, respx
from aptx.core import http

@respx.mock
def test_sends_user_agent_and_retries_429():
    route = respx.get("https://example.test/x").mock(side_effect=[
        httpx.Response(429), httpx.Response(200, json={"ok": True})])
    http.MIN_INTERVAL = 0
    http.BACKOFF_BASE = 0
    assert http.get_json("https://example.test/x") == {"ok": True}
    assert route.call_count == 2
    assert route.calls[0].request.headers["user-agent"].startswith("apt-explorer/")
