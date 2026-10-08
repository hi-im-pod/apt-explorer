"""Report titles that are file names, placeholders or error pages.

Sources often take a report's title from the file's own metadata or from the page a link now
leads to. That gives "Microsoft Word - TR62.doc", "PowerPoint Presentation" or
"404: This page could not be found." Only titles of those shapes are changed here. A title
that reads as a sentence is left alone, so "404 Keylogger Campaigns" keeps its name.
"""
import re
from urllib.parse import unquote, urlsplit

# Prefixes an application or a desktop file system writes in front of the file name.
_APP_PREFIX = re.compile(r"^Microsoft (?:Word|PowerPoint|Excel) - ", re.I)
_MAC_PATH = re.compile(r"^Macintosh HD:(?:[^:]*:)*")
# Only document formats count. ".net", ".com" or ".A" end many real titles and malware names.
_DOC_EXTENSION = re.compile(r"\.(?:pdf|docx?|pptx?|xlsx?|rtf|txt|indd|indb|pmd|key|odt)$", re.I)
_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")
# "securelist.com-The Icefog APT...": the lab corpus files some papers under the site they came from.
_DOMAIN_PREFIX = re.compile(r"^((?:[a-z0-9-]+\.)+[a-z]{2,})-(?=[A-Za-z0-9])")

# Titles that name a template or a blank document, not the report. Compared case-insensitively.
_PLACEHOLDERS = frozenset({
    "powerpoint presentation", "powerpoint-präsentation", "powerpoint プレゼンテーション", "powerpoint 簡報",
    "word template", "untitled", "title",
})
# The page a dead link now leads to. Exact shapes only: a post may well be called "404 Keylogger Campaigns".
_ERROR_PAGE = re.compile(
    r"^(?:404|not found|page not found|(?:404: )?this page could not be found\.?|file not found · \S+)$", re.I)


def is_error_page(title: str | None) -> bool:
    return bool(title) and bool(_ERROR_PAGE.match(" ".join(title.split())))


def title_domain(title: str | None) -> str | None:
    """The site a "domain-Title" prefix names, such as securelist.com, or None."""
    m = _DOMAIN_PREFIX.match((title or "").strip())
    return m.group(1) if m else None


def clean_title(title: str | None) -> str | None:
    """The title a reader should see, or None when it names no report.

    Whitespace runs become one space. A file-name title loses its application or path prefix,
    its percent-encoding and its document extension, and, when it has no spaces, its
    underscores. Placeholders and error pages give None, so another copy's title or the
    address is shown instead.
    """
    if not isinstance(title, str):
        return None
    text = " ".join(title.split())
    if not text or text.casefold() in _PLACEHOLDERS or is_error_page(text):
        return None
    if _PERCENT.search(text):
        text = " ".join(unquote(text).split())
    text = _MAC_PATH.sub("", _APP_PREFIX.sub("", text))
    text = _DOMAIN_PREFIX.sub("", text)
    file_name = bool(_DOC_EXTENSION.search(text))
    text = _DOC_EXTENSION.sub("", text)
    # "Anunak_APT_against_financial_institutions". One underscore is kept, because malware names
    # such as BKDR_SARHUST.A are written that way.
    if " " not in text and (file_name or text.count("_") >= 3):
        text = text.replace("_", " ")
    # Removing a prefix or an extension can leave a space at either end: "LIFARS- Lazarus .pdf".
    return " ".join(text.split()) or None


# A path segment that is only an ID, a date part or a language code says nothing about the report.
_NO_WORDS = re.compile(r"^(?:[0-9]+|[a-z]{2}(?:[-_][a-z]{2})?|index|default|article|post|blog|news)$", re.I)
_WORD = re.compile(r"[A-Za-z]{2,}")
# Medium and some CMSs end a slug with a post ID: "...-for-proactive-detection-34055a017e56".
_TRAILING_ID = re.compile(r"[-_](?=[0-9a-f]*[0-9])[0-9a-f]{8,}$", re.I)


def title_from_url(url: str | None) -> str | None:
    """A title read from the address's last meaningful path segment, or None.

    "https://blogs.blackberry.com/en/2019/07/threat-spotlight-sodinokibi" gives
    "Threat spotlight sodinokibi". A segment needs two words or more, so an article number or
    "showcard.cgi" gives nothing.
    """
    path = urlsplit(url or "").path
    for segment in reversed([unquote(p) for p in path.split("/") if p]):
        segment = _DOC_EXTENSION.sub("", re.sub(r"\.(?:html?|php|aspx?|cgi)$", "", segment, flags=re.I))
        segment = _TRAILING_ID.sub("", segment)
        if _NO_WORDS.match(segment):
            continue
        words = " ".join(re.split(r"[-_+\s]+", segment)).strip()
        # A hash or an ID is not a name, even when its letters happen to make two "words".
        if len(_WORD.findall(words)) < 2 or re.fullmatch(r"[0-9a-f]{16,}", segment, re.I):
            return None
        return words[0].upper() + words[1:]
    return None
