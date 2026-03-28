"""Tests for RSS feed ingestion."""

from scripts.ingestion.ingest_rss_feeds import (
    parse_atom_feed,
    parse_feed,
    parse_rss_feed,
)

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>Article One</title>
    <link>https://example.com/article-1</link>
    <guid>article-1-guid</guid>
    <pubDate>Mon, 01 Jan 2026 00:00:00 GMT</pubDate>
    <description>First article description.</description>
  </item>
  <item>
    <title>Article Two</title>
    <link>https://example.com/article-2</link>
    <guid>article-2-guid</guid>
    <description>Second article description.</description>
  </item>
</channel>
</rss>"""


SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>Atom Entry One</title>
    <link href="https://example.com/atom-1"/>
    <id>atom-entry-1</id>
    <summary>Atom entry summary.</summary>
  </entry>
</feed>"""


def test_parse_rss_feed():
    """parse_rss_feed extracts items from RSS XML."""
    entries = parse_rss_feed(SAMPLE_RSS)
    assert len(entries) == 2
    assert entries[0]["title"] == "Article One"
    assert entries[0]["url"] == "https://example.com/article-1"
    assert entries[0]["guid"] == "article-1-guid"


def test_parse_atom_feed():
    """parse_atom_feed extracts entries from Atom XML."""
    entries = parse_atom_feed(SAMPLE_ATOM)
    assert len(entries) == 1
    assert entries[0]["title"] == "Atom Entry One"
    assert entries[0]["url"] == "https://example.com/atom-1"
    assert entries[0]["guid"] == "atom-entry-1"


def test_parse_feed_auto_detects_rss():
    """parse_feed auto-detects RSS format."""
    entries = parse_feed(SAMPLE_RSS)
    assert len(entries) == 2


def test_parse_feed_auto_detects_atom():
    """parse_feed auto-detects Atom format."""
    entries = parse_feed(SAMPLE_ATOM)
    assert len(entries) == 1


def test_parse_feed_empty():
    """parse_feed returns empty list for invalid XML."""
    entries = parse_feed("<html><body>Not a feed</body></html>")
    assert entries == []
