"""Three security vendors' blog feeds, as titles, dates, links and stated name pairs.

None of these publishers grants a licence to reuse its posts, and the terms
of each are ambiguous about links, so SOURCES.md lists every one as
derived-only and each is its own source. A post's text is read in memory for
pairs of names it says are one actor, and only the two names are kept. Removing one means deleting its class
here and its entries in cli.py, notice.py, similarity.py, assemble.py,
labels.ts and SOURCES.md.

None of the three pages through older posts, because each feed publishes
only its newest posts.
"""
from aptx.sources.feed import FeedConnector


class TalosConnector(FeedConnector):
    name = "talos"
    feed_url = "https://blog.talosintelligence.com/rss/"
    organisation = "Cisco Talos"
    host = "blog.talosintelligence.com"
    read_pairs = True


class EsetConnector(FeedConnector):
    name = "eset"
    feed_url = "https://www.welivesecurity.com/en/feed/"
    organisation = "ESET Research"
    host = "welivesecurity.com"
    read_pairs = True
    # The feed is the whole blog, including scam and consumer advice posts.
    # Posts from ESET's research team sit under this path.
    path_prefix = "/en/eset-research/"


class MicrosoftBlogConnector(FeedConnector):
    # The key "microsoft" is the threat actor naming table, a different source.
    name = "microsoftblog"
    feed_url = "https://www.microsoft.com/en-us/security/blog/feed/"
    organisation = "Microsoft Security"
    host = "microsoft.com"
    read_pairs = True
