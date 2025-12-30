"""
Shared utilities for crawl tools.
"""
from __future__ import annotations

import logging
from typing import Union
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class FirecrawlSearchWrapperInput(BaseModel):
    """Input schema for Firecrawl Search Wrapper tool."""

    query: Union[str, dict] = Field(
        ..., description="The search query as a plain text string. Example: 'data science trends 2025'"
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v):
        """Normalize input - handle both strings and dicts from Ollama."""
        if isinstance(v, dict):
            if "query" in v:
                return v["query"]
            if "description" in v:
                desc = v["description"]
                if isinstance(desc, str) and len(desc) > 5:
                    return desc
            if "value" in v:
                return v["value"]

            for _, value in v.items():
                if isinstance(value, str) and len(value) > 5:
                    return value
            return str(v)

        if isinstance(v, str):
            return v

        return str(v)


def filter_problematic_urls(result: dict) -> dict:
    """Filter out URLs that are likely paywalled, require auth, or timed out.
    
    This is a shared helper function used by both FirecrawlSearchWrapper
    and SelfHostedFirecrawlSearchTool to filter problematic URLs.
    """
    if not isinstance(result, dict):
        return result
    
    # Known problematic domains (paywalled, require auth, etc.)
    problematic_domains = {
        'jstor.org', 'sciencedirect.com', 'ieee.org', 'acm.org',
        'springer.com', 'nature.com', 'elsevier.com', 'wiley.com',
        'tandfonline.com', 'sagepub.com', 'oup.com', 'cambridge.org',
        'pubmed.ncbi.nlm.nih.gov', 'arxiv.org/pdf', 'researchgate.net',
        'academia.edu', 'semanticscholar.org'
    }
    
    # Filter data array if present
    if 'data' in result and isinstance(result['data'], list):
        original_count = len(result['data'])
        filtered_data = []
        for item in result['data']:
            if isinstance(item, dict):
                url = item.get('url', '') or item.get('link', '') or item.get('source', '')
                # Skip if URL is from problematic domain
                if url and any(domain in url.lower() for domain in problematic_domains):
                    logger.info(f"Skipping paywalled/problematic URL: {url}")
                    continue
                # Skip if there's an error or timeout
                error_msg = item.get('error', '') or item.get('errorMessage', '') or ''
                if error_msg or 'timeout' in str(error_msg).lower() or 'timed out' in str(error_msg).lower():
                    logger.info(f"Skipping failed URL (error/timeout): {url}")
                    continue
                # Skip if content is empty or too short (likely failed scrape)
                content = item.get('content', '') or item.get('markdown', '') or item.get('text', '') or item.get('description', '')
                if not content or len(str(content).strip()) < 50:
                    logger.info(f"Skipping URL with insufficient content: {url}")
                    continue
            filtered_data.append(item)
        result['data'] = filtered_data
        if original_count > len(filtered_data):
            result['filtered_count'] = original_count - len(filtered_data)
            logger.info(f"Filtered {result['filtered_count']} problematic URLs from {original_count} results")
    
    return result

