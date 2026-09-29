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

# Servers that refuse HEAD answer with one of these. The same URL usually
# works for GET, so a refusal is not proof that the link is dead.
_HEAD_REFUSED = frozenset({400, 403, 405, 501})
LINK_TIMEOUT = 20.0

def probe(url: str) -> int:
    """The final status code of a URL, without downloading its body.

    Sends HEAD and falls back to GET when the server refuses HEAD. Every
    request goes through the same per-host pacing as the connectors, so a
    link check of many pages on one site stays polite. Unlike the fetch
    helpers this makes one attempt per method and never retries: a link
    checker wants to know what the server said, and retrying a 5xx would only
    slow the check down. A transport failure such as a timeout is raised for
    the caller to record.
    """
    _pace(url)
    status = _client.head(url, timeout=LINK_TIMEOUT).status_code
    if status in _HEAD_REFUSED:
        _pace(url)
        # stream() reads the headers only, so the body is never downloaded.
        with _client.stream("GET", url, timeout=LINK_TIMEOUT) as r:
            status = r.status_code
    return status
