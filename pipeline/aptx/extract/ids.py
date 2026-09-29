"""CVE and ATT&CK technique IDs found in free report text."""
import re

# PDF extraction often turns the hyphens in an ID into a non-breaking hyphen
# or a dash, so every such character counts as a separator. re.ASCII keeps \b,
# \w and \d to ASCII, so digits from other scripts never form an ID.
_DASH = "[-‐‑‒–—−]"
_CVE = re.compile(rf"\bCVE{_DASH}(\d{{4}}){_DASH}(\d{{4,7}})(?!\w)", re.ASCII | re.IGNORECASE)
# The leading \b keeps "ST1059" out. The trailing check keeps "T10590" and
# "T1059.0015" out instead of reading them as T1059, while a full stop that
# ends a sentence, as in "T1566.", still ends the ID.
_TECHNIQUE = re.compile(r"\bT\d{4}(?:\.\d{3})?(?!\w|\.\d)", re.ASCII)


def find_cves(text: str | None) -> list[str]:
    """Every CVE ID in the text, upper case, unique and sorted."""
    return sorted({f"CVE-{m.group(1)}-{m.group(2)}" for m in _CVE.finditer(text or "")})


def technique_candidates(text: str | None) -> list[str]:
    """Every well-formed technique ID in the text, unique and sorted.

    The list is not checked against ATT&CK. A "T" followed by four digits also
    appears in part numbers and ticket IDs, so callers publish only the IDs
    that find_techniques() accepts.
    """
    return sorted({m.group(0) for m in _TECHNIQUE.finditer(text or "")})


def find_techniques(text: str | None, valid: set[str] | frozenset[str]) -> list[str]:
    """The technique IDs in the text that ATT&CK defines, unique and sorted.

    `valid` holds the technique and sub-technique IDs of the current ATT&CK
    release. An ID outside it is dropped, even when its parent technique
    exists, so a mistyped sub-technique never reaches the site.
    """
    return [t for t in technique_candidates(text) if t in valid]
