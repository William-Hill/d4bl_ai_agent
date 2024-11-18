from research_agent import ResearchAgent, sanitize_filename, save_results
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

def main():
    # Initialize the research agent
    agent = ResearchAgent()
    
    # Define search query
    query = 'What are the trade-offs between open data initiatives and individual privacy?'
    
    # Perform research and get results
    results = agent.research(query)
    
    # Save results using the standalone functions
    filename = save_results(query, results['results'])
    
    # Pretty print the results
    print("\n=== Search Results ===")
    print(f"Query: {query}")
    print("\nResults:")
    print(results['results'])
    print("\nFull Response:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults saved to: {filename}")

    # You can also get the sanitized filename separately if needed
    sanitized_query = sanitize_filename(query)
    print(f"\nSanitized query: {sanitized_query}")

if __name__ == "__main__":
    main()