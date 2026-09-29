"""One URL normalizer for every lookup that joins sources by link.

Malpedia's library dates are keyed by URL, and ORKL, the paper and The DFIR
Report cite the same reports with different schemes, a www. prefix, a
trailing slash or different letter case. Both sides of any such join must go
through norm_url, or matching reports never meet.
"""
import re

_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://")


def norm_url(url: str) -> str:
    """The URL lowercased, without its scheme, a leading "www." or a trailing "/".

    "https://www.Example.com/a/" and "http://example.com/a" both become
    "example.com/a".
    """
    u = _SCHEME.sub("", url.strip().lower())
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")
