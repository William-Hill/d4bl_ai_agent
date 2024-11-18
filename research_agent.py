from crewai import Agent
from crewai_tools import FirecrawlSearchTool
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import re

load_dotenv()

def sanitize_filename(query: str) -> str:
    """Convert query to a valid filename"""
    sanitized = re.sub(r'[^\w\s-]', '', query)
    sanitized = re.sub(r'[-\s]+', '_', sanitized)
    return sanitized.lower()[:50]

def save_results(query: str, results: str) -> str:
    """Save results to a JSON file and return the filename"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query_part = sanitize_filename(query)
    filename = f"search_results_{query_part}_{timestamp}.json"
    
    try:
        data = {
            "query": query,
            "timestamp": timestamp,
            "results": results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        return filename
    except Exception as e:
        print(f"Error saving results: {e}")
        return None

class ResearchAgent:
    def __init__(self):
        self.firecrawl_tool = FirecrawlSearchTool(
            api_key=os.getenv("FIRECRAWL_API_KEY"),
            max_pages=3,  # Limit to 3 pages
            max_results=5  # Limit to 5 results per page
        )
        
    def create_agent(self) -> Agent:
        return Agent(
            role='Research Analyst',
            goal='Conduct thorough web research and provide comprehensive analysis on given topics',
            backstory="""You are an expert research analyst with a keen eye for detail 
            and the ability to synthesize complex information from multiple sources. 
            You excel at finding relevant information and presenting it in a clear, 
            organized manner.""",
            tools=[self.firecrawl_tool],
            verbose=True,
            allow_delegation=False
        )
    
    def research(self, query: str, max_content_length: int = 2000) -> dict:
        """
        Perform research on a given query and save results
        
        Args:
            query (str): The research query to investigate
            max_content_length (int): Maximum length of content to return per result
            
        Returns:
            dict: Research results and metadata
        """
        print(f"\nResearching: {query}")
        print(f"Max content length: {max_content_length} characters")
        
        # Execute the search
        results = self.firecrawl_tool.run(query=query)
        
        # Truncate results if they're too long
        if isinstance(results, str) and len(results) > max_content_length:
            print(f"Truncating results from {len(results)} to {max_content_length} characters")
            results = results[:max_content_length] + "..."
        
        # Save results to file
        filename = save_results(query, results)
        
        print(f"Research completed. Results length: {len(results) if isinstance(results, str) else 'N/A'}")
        return {
            "query": query,
            "results": results,
            "filename": filename
        }

def main():
    # Example usage
    agent = ResearchAgent()
    researcher = agent.create_agent()
    
    # Example research task
    research_task = """
    Research the latest developments in quantum computing and its potential impact 
    on cryptography. Focus on:
    1. Recent breakthroughs
    2. Potential threats to current encryption methods
    3. Proposed solutions for quantum-resistant cryptography
    """
    
    results = agent.research(research_task)
    
    # print("\n=== Search Results ===")
    # print(f"Query: {results['query']}")
    # print("\nResults:")
    # print(json.dumps(results['results'], indent=2, ensure_ascii=False))
    # print(f"\nResults saved to: {results['filename']}")
    print("Research completed.")

if __name__ == "__main__":
    main() 