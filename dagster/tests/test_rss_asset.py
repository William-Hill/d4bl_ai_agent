"""Unit tests for the RSS/Atom feed asset factory."""

import xml.etree.ElementTree as ET

from d4bl_pipelines.assets.feeds.rss_monitor import (
    _parse_atom,
    _parse_feed,
    _parse_rss,
    _slugify,
    build_rss_assets,
)

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>A test RSS feed</description>
    <item>
      <title>First Post</title>
      <link>https://example.com/first</link>
      <description>Description of first post</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
      <guid>https://example.com/first</guid>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://example.com/second</link>
      <description>Description of second post</description>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
      <guid>https://example.com/second</guid>
    </item>
  </channel>
</rss>
"""

SAMPLE_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <link href="https://example.com"/>
  <entry>
    <title>Atom Entry One</title>
    <link href="https://example.com/atom-one"/>
    <summary>Summary of atom entry one</summary>
    <updated>2024-01-01T00:00:00Z</updated>
    <id>urn:uuid:entry-one</id>
  </entry>
  <entry>
    <title>Atom Entry Two</title>
    <link href="https://example.com/atom-two"/>
    <content>Content of atom entry two</content>
    <published>2024-01-02T00:00:00Z</published>
    <id>urn:uuid:entry-two</id>
  </entry>
</feed>
"""


class TestParseRss:
    def test_extracts_all_items(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert len(entries) == 2

    def test_extracts_title(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert entries[0]["title"] == "First Post"
        assert entries[1]["title"] == "Second Post"

    def test_extracts_link(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert entries[0]["link"] == "https://example.com/first"

    def test_extracts_description(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert entries[0]["description"] == "Description of first post"

    def test_extracts_published(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert entries[0]["published"] == (
            "Mon, 01 Jan 2024 00:00:00 GMT"
        )

    def test_extracts_guid(self):
        entries = _parse_rss(ET.fromstring(SAMPLE_RSS))
        assert entries[0]["guid"] == "https://example.com/first"


class TestParseAtom:
    def test_extracts_all_entries(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert len(entries) == 2

    def test_extracts_title(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[0]["title"] == "Atom Entry One"

    def test_extracts_link_from_href(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[0]["link"] == "https://example.com/atom-one"

    def test_extracts_summary_as_description(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[0]["description"] == (
            "Summary of atom entry one"
        )

    def test_falls_back_to_content(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[1]["description"] == (
            "Content of atom entry two"
        )

    def test_extracts_updated_as_published(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[0]["published"] == "2024-01-01T00:00:00Z"

    def test_falls_back_to_published_date(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[1]["published"] == "2024-01-02T00:00:00Z"

    def test_extracts_id_as_guid(self):
        entries = _parse_atom(ET.fromstring(SAMPLE_ATOM))
        assert entries[0]["guid"] == "urn:uuid:entry-one"


class TestParseFeed:
    def test_detects_rss(self):
        entries = _parse_feed(SAMPLE_RSS)
        assert len(entries) == 2
        assert entries[0]["title"] == "First Post"

    def test_detects_atom(self):
        entries = _parse_feed(SAMPLE_ATOM)
        assert len(entries) == 2
        assert entries[0]["title"] == "Atom Entry One"


class TestSlugify:
    def test_basic(self):
        assert _slugify("My Feed Name") == "my_feed_name"

    def test_special_chars(self):
        assert _slugify("RSS: News & Updates!") == (
            "rss_news_updates"
        )

    def test_empty(self):
        assert _slugify("") == "unnamed_source"

    def test_leading_trailing(self):
        assert _slugify("  --hello-- ") == "hello"


class TestBuildRssAssets:
    def _make_source(self, name="Test Feed", source_type="rss_feed"):
        return {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "name": name,
            "source_type": source_type,
            "config": {
                "feed_url": "https://example.com/feed.xml",
                "max_entries": 50,
                "crawl_linked": False,
            },
        }

    def test_returns_assets_for_rss_sources(self):
        sources = [self._make_source()]
        assets = build_rss_assets(sources)
        assert len(assets) == 1

    def test_filters_non_rss_sources(self):
        sources = [
            self._make_source(name="API Source", source_type="api"),
            self._make_source(
                name="File Source", source_type="file_upload"
            ),
            self._make_source(name="RSS One", source_type="rss_feed"),
        ]
        assets = build_rss_assets(sources)
        assert len(assets) == 1

    def test_empty_list(self):
        assets = build_rss_assets([])
        assert assets == []

    def test_asset_group_name(self):
        sources = [self._make_source()]
        assets = build_rss_assets(sources)
        # AssetsDefinition exposes group_names_by_key
        for key, group in assets[0].group_names_by_key.items():
            assert group == "feeds"

    def test_multiple_rss_sources(self):
        sources = [
            self._make_source(name="Feed A"),
            self._make_source(name="Feed B"),
        ]
        assets = build_rss_assets(sources)
        assert len(assets) == 2
