"""The one HTTP client every connector uses.

Each source is a free service run by someone else. A shared client lets us
identify ourselves and stay polite with every source in one place, rather than
trusting each connector to remember.
"""
import time
from urllib.parse import urlparse
import httpx

# The contact URL tells a source operator who is fetching and how to reach them
# before they decide to block us.
USER_AGENT = "apt-explorer/0.1 (+https://github.com/hi-im-pod)"
MIN_INTERVAL = 1.0      # seconds between requests to one host
BACKOFF_BASE = 2.0
TRIES = 3
# These are module globals, not constants inside the functions, so tests can
# set the waits to zero and stay fast.
_last: dict[str, float] = {}
_client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)

def _pace(url: str) -> None:
    # Pacing is per host, so a slow source such as Malpedia never holds up
    # requests to the others.
    host = urlparse(url).netloc
    wait = _last.get(host, 0) + MIN_INTERVAL - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.monotonic()

def _get(url: str, params=None) -> httpx.Response:
    # A 429 or 5xx usually means "not right now", so we back off and retry.
    # Any other error status means the request itself is wrong, and retrying
    # would not help.
    for attempt in range(TRIES):
        _pace(url)
        r = _client.get(url, params=params)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(BACKOFF_BASE * (2 ** attempt))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

def get_json(url: str, params=None):
    return _get(url, params).json()

def get_text(url: str) -> str:
    return _get(url).text

def get_bytes(url: str) -> bytes:
    return _get(url).content
