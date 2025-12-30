#!/bin/bash

# Test script to verify Firecrawl is working
# Usage: ./test_firecrawl.sh [API_KEY]

FIRECRAWL_BASE_URL="${FIRECRAWL_BASE_URL:-http://localhost:3003}"
API_KEY="${1:-${FIRECRAWL_API_KEY}}"

echo "Testing Firecrawl at: $FIRECRAWL_BASE_URL"
echo "=========================================="
echo ""

# Test 1: Health check (if available)
echo "1. Testing health endpoint..."
curl -s "$FIRECRAWL_BASE_URL/health" || echo "Health endpoint not available"
echo ""
echo ""

# Test 2: Scrape a simple URL
echo "2. Testing scrape endpoint..."
if [ -z "$API_KEY" ]; then
    echo "   No API key provided - testing without auth"
    curl -X POST "$FIRECRAWL_BASE_URL/v0/scrape" \
        -H "Content-Type: application/json" \
        -d '{
            "url": "https://example.com",
            "formats": ["markdown"]
        }' \
        -w "\nHTTP Status: %{http_code}\n"
else
    echo "   Testing with API key"
    curl -X POST "$FIRECRAWL_BASE_URL/v0/scrape" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "url": "https://example.com",
            "formats": ["markdown"]
        }' \
        -w "\nHTTP Status: %{http_code}\n"
fi
echo ""
echo ""

# Test 3: Search endpoint (if available)
echo "3. Testing search endpoint..."
if [ -z "$API_KEY" ]; then
    echo "   No API key provided - testing without auth"
    curl -X POST "$FIRECRAWL_BASE_URL/v0/search" \
        -H "Content-Type: application/json" \
        -d '{
            "query": "artificial intelligence",
            "pageOptions": {
                "maxResults": 3
            }
        }' \
        -w "\nHTTP Status: %{http_code}\n"
else
    echo "   Testing with API key"
    curl -X POST "$FIRECRAWL_BASE_URL/v0/search" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_KEY" \
        -d '{
            "query": "artificial intelligence",
            "pageOptions": {
                "maxResults": 3
            }
        }' \
        -w "\nHTTP Status: %{http_code}\n"
fi
echo ""
echo ""

echo "=========================================="
echo "Test complete!"
echo ""
echo "If you see HTTP 200 responses, Firecrawl is working correctly."
echo "If you see HTTP 401, you may need to provide an API key."
echo "If you see connection errors, check that Firecrawl is running:"
echo "  docker compose ps firecrawl-api"

