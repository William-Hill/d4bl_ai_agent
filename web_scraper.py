from firecrawl import FirecrawlApp
import argparse
from typing import List, Dict
import json
import os
from dotenv import load_dotenv

load_dotenv()

class WebScraper:
    def __init__(self):
        # self.crawler = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        self.crawler = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        
    def search_and_scrape(self, prompt: str, max_pages: int = 3) -> List[Dict]:
        """
        Search and scrape web content based on user prompt
        
        Args:
            prompt (str): Search query or topic to crawl
            max_pages (int): Maximum number of pages to crawl
            
        Returns:
            List[Dict]: List of scraped results with URLs and content
        """
        # Configure crawler settings
        self.crawler.configure(
            max_pages=max_pages,
            follow_links=False,
            respect_robots=True,
            delay=1.0,
            max_content_length=2000
        )
        
        # Start the crawl based on prompt
        results = self.crawler.search(prompt)
        
        # Process and store scraped data
        scraped_data = []
        for result in results:
            data = {
                'url': result.url,
                'title': result.title,
                'content': result.text,
                'metadata': {
                    'timestamp': result.timestamp,
                    'keywords': result.keywords
                }
            }
            scraped_data.append(data)
            
        return scraped_data

def main():
    parser = argparse.ArgumentParser(description='Web scraper using Firecrawl')
    parser.add_argument('prompt', type=str, help='Search query or topic to crawl')
    parser.add_argument('--max-pages', type=int, default=5, help='Maximum number of pages to crawl')
    parser.add_argument('--output', type=str, default='scraped_data.json', help='Output file path')
    
    args = parser.parse_args()
    
    # Initialize and run scraper
    scraper = WebScraper()
    results = scraper.search_and_scrape(args.prompt, args.max_pages)
    
    # Save results to file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Scraped {len(results)} pages. Results saved to {args.output}")

if __name__ == "__main__":
    main() 