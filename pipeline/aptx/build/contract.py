"""Which JSON Schema governs each file under data/.

The pipeline writes data/ and the site reads it, and the two are built
separately. The schemas in schemas/ are the only agreement between them. The
writer validates every file against them before anything is written, and the
tests validate the committed data/ against the same mapping, so the two checks
cannot disagree about which schema a file answers to.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

# Files in data/ that no schema governs, named one by one so that any other
# stray file still fails the contract tests. NOTICE.md carries the data licence
# and the attributions that CC BY-NC-SA and MITRE's licence require in every
# copy of data/, so a writer that clears data/ before a build must keep it.
NON_JSON_FILES = frozenset({"NOTICE.md"})

# Paths are relative to data/. The first rule that matches wins, which is why
# actors/index.json comes before the rule for single actor pages.
_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"actors/index\.json"), "actors_index"),
    (re.compile(r"actors/[^/]+\.json"), "actor"),
    (re.compile(r"reports/(?:[0-9]{4}|undated)\.json"), "reports_shard"),
    (re.compile(r"campaigns\.json"), "campaigns"),
    (re.compile(r"vulns\.json"), "vulns"),
    (re.compile(r"sources\.json"), "sources"),
    (re.compile(r"resolution\.json"), "resolution"),
    (re.compile(r"trends\.json"), "trends"),
    (re.compile(r"guesses\.json"), "guesses"),
    (re.compile(r"build\.json"), "build"),
    (re.compile(r"slugs\.json"), "slugs"),
)


def schema_for(relpath: str) -> str | None:
    """The schema name for a path under data/, or None when no schema covers it.

    Windows separators are accepted, so a path built with pathlib on Windows
    maps the same way as one built on the Linux build runner.
    """
    rel = relpath.replace("\\", "/")
    for pattern, name in _RULES:
        if pattern.fullmatch(rel):
            return name
    return None


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    """The parsed schema. It is cached and shared, so callers must not modify it."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    """A validator for one schema.

    Formats are left unchecked on purpose. Every date and ID in the schemas is
    constrained by an anchored pattern instead, because jsonschema treats
    `format` as an annotation unless a format checker is passed, and a check
    that silently does nothing is worse than none.
    """
    return Draft202012Validator(load_schema(name))
