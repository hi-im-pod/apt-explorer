"""The DFIR Report's RSS feed, as titles, dates and links only.

The DFIR Report reserves all rights to its text, and SOURCES.md lists it as
link-only. See feed.py for what a snapshot keeps. The live feed shows ten
posts, so older ones are read from its numbered pages.
"""
from aptx.sources.feed import SNAPSHOT, FeedConnector

FEED_URL = "https://thedfirreport.com/feed/"
ORGANISATION = "The DFIR Report"
HOST = "thedfirreport.com"

__all__ = ["DfirConnector", "FEED_URL", "SNAPSHOT"]


class DfirConnector(FeedConnector):
    name = "dfir"
    feed_url = FEED_URL
    organisation = ORGANISATION
    host = HOST
    page_param = "paged"
