"""
Crawl provider tooling shared between Crawl4AI and Firecrawl.

This package isolates crawling/search concerns away from crew wiring to keep `crew.py`
smaller and easier to test.
"""
from __future__ import annotations

from d4bl.agents.tools.crawl_tools.firecrawl import (
    FirecrawlSearchWrapper,
    FirecrawlSearchWrapperInput,
    SelfHostedFirecrawlSearchTool,
)
from d4bl.agents.tools.crawl_tools.crawl4ai import Crawl4AISearchTool

__all__ = [
    "Crawl4AISearchTool",
    "FirecrawlSearchWrapper",
    "FirecrawlSearchWrapperInput",
    "SelfHostedFirecrawlSearchTool",
]

