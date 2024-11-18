from typing import Dict
from research_agent import ResearchAgent
from data_analyst_agent import DataAnalystAgent
from writer_agent import WriterAgent
from dotenv import load_dotenv
import json
from datetime import datetime
import argparse
import traceback
import os

load_dotenv()

class D4BLResearchAnalyzer:
    def __init__(self):
        self.research_agent = ResearchAgent()
        self.analyst_agent = DataAnalystAgent()
        self.writer_agent = WriterAgent()
        
        # Create error_logs directory if it doesn't exist
        self.error_logs_dir = 'error_logs'
        os.makedirs(self.error_logs_dir, exist_ok=True)
        
    def _log_error(self, error_type: str, error: Exception, details: Dict = None) -> str:
        """Log error details to a file and return the filename"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create subdirectory for error type
        error_type_dir = os.path.join(self.error_logs_dir, error_type)
        os.makedirs(error_type_dir, exist_ok=True)
        
        filename = os.path.join(error_type_dir, f"error_{timestamp}.json")
        
        error_data = {
            "timestamp": timestamp,
            "error_type": error_type,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "details": details or {}
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)
            
        return filename
        
    def analyze_topic(self, query: str, summary_format: str = None) -> Dict:
        """
        Research and analyze a D4BL-related topic
        """
        print(f"\n=== Starting D4BL Research: {query} ===")
        
        try:
            # Step 1: Conduct initial research
            print("\nConducting research...")
            try:
                research_results = self.research_agent.research(query)
                # print(f"Research completed. Results type: {type(research_results)}")
                # print(f"Research keys: {list(research_results.keys())}")
            except Exception as e:
                error_file = self._log_error("research", e, {"query": query})
                # print(f"Research error logged to: {error_file}")
                raise
            
            # Step 2: Analyze the research results
            print("\nAnalyzing research data...")
            try:
                analysis = self.analyst_agent.analyze_research_results(research_results)
                print(f"Analysis completed. Structure: {list(analysis.keys())}")
                if 'error' in analysis.get('analysis', {}):
                    error_file = self._log_error(
                        "analysis_warning", 
                        Exception(analysis['analysis']['error']),
                        {"research_results": research_results}
                    )
                    print(f"Analysis warning logged to: {error_file}")
            except Exception as e:
                error_file = self._log_error("analysis", e, {
                    "query": query,
                    "research_results": research_results
                })
                print(f"Analysis error logged to: {error_file}")
                analysis = {
                    "analysis": {
                        "key_points": [],
                        "main_themes": [],
                        "data_quality": {
                            "completeness": 0.0,
                            "relevance": 0.0,
                            "reliability": 0.0
                        },
                        "recommendations": [],
                        "error": str(e)
                    }
                }
            
            # Step 3: Combine results
            combined_results = {
                "query": query,
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "research": research_results,
                "analysis": analysis
            }
            
            # Print structure before summary generation
            print("\nCombined results structure:")
            print(f"Keys: {list(combined_results.keys())}")
            print(f"Analysis keys: {list(combined_results['analysis'].keys())}")
            
            # Step 4: Generate written summary if requested
            if summary_format:
                print(f"\nGenerating {summary_format} summary...")
                try:
                    summary = self.writer_agent.write_summary(combined_results, summary_format)
                    print("Summary generated successfully")
                    print(f"Summary keys: {list(summary.keys())}")
                    combined_results["written_summary"] = summary
                except Exception as e:
                    error_file = self._log_error("summary", e, {
                        "query": query,
                        "summary_format": summary_format,
                        "combined_results": combined_results
                    })
                    print(f"Summary generation error logged to: {error_file}")
                    combined_results["written_summary"] = {
                        "error": str(e),
                        "query": query,
                        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
                    }
            
            # Save combined results
            try:
                filename = self._save_combined_results(combined_results)
                print(f"\nResults saved to: {filename}")
            except Exception as e:
                error_file = self._log_error("save_results", e, {
                    "combined_results": combined_results
                })
                print(f"Error saving results logged to: {error_file}")
                raise
            
            return combined_results
            
        except Exception as e:
            error_file = self._log_error("general", e, {"query": query})
            print(f"General error logged to: {error_file}")
            return {
                "error": str(e),
                "error_log": error_file,
                "query": query,
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
            }
    
    def _save_combined_results(self, results: Dict) -> str:
        """Save the combined research and analysis results"""
        timestamp = results["timestamp"]
        query_part = results["query"][:50].lower().replace(" ", "_")
        filename = f"d4bl_research_{query_part}_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        return filename

def print_results(results: Dict):
    """Pretty print the research and analysis results"""
    print("\n=== D4BL Research and Analysis Results ===")
    print(f"\nQuery: {results['query']}")
    print(f"Timestamp: {results['timestamp']}")
    
    print("\n=== Key Findings ===")
    print("\nKey Points:")
    for point in results['analysis']['analysis']['key_points']:
        print(f"- {point}")
    
    print("\nMain Themes:")
    for theme in results['analysis']['analysis']['main_themes']:
        print(f"- {theme}")
    
    print("\nData Quality Assessment:")
    quality = results['analysis']['analysis']['data_quality']
    print(f"- Completeness: {quality['completeness']:.2f}")
    print(f"- Relevance: {quality['relevance']:.2f}")
    print(f"- Reliability: {quality['reliability']:.2f}")
    
    print("\nRecommendations:")
    for rec in results['analysis']['analysis']['recommendations']:
        print(f"- {rec}")

def main():
    parser = argparse.ArgumentParser(description='D4BL Research and Analysis Tool')
    parser.add_argument(
        'query',
        type=str,
        nargs='?',  # Make query optional
        help='Research query or topic to investigate'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='full',
        choices=['full', 'summary'],
        help='Output format (full or summary)'
    )
    parser.add_argument(
        '--summary',
        type=str,
        choices=['brief', 'detailed', 'comprehensive'],
        help='Generate a written summary of specified length'
    )
    
    args = parser.parse_args()
    
    # Example D4BL research topics
    example_topics = [
        "How does algorithmic bias affect criminal justice outcomes for Black communities?",
        "What are the impacts of data-driven policing on Black neighborhoods?",
        "How can data science be used to address racial disparities in healthcare?",
        "What role does big data play in perpetuating housing discrimination?"
    ]
    
    # If no query provided, prompt user
    if not args.query:
        print("\nExample Research Topics:")
        for i, topic in enumerate(example_topics, 1):
            print(f"{i}. {topic}")
        print("\n0. Enter custom query")
        
        while True:
            try:
                choice = input("\nSelect a topic number (0-4): ")
                if choice == '0':
                    args.query = input("\nEnter your research query: ")
                    break
                elif choice.isdigit() and 1 <= int(choice) <= len(example_topics):
                    args.query = example_topics[int(choice) - 1]
                    break
                else:
                    print("Invalid choice. Please select a number between 0 and 4.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    
    # If no summary type provided, prompt user
    if not args.summary:
        print("\nSummary Types:")
        print("1. Brief (250-500 words)")
        print("2. Detailed (1000-1500 words)")
        print("3. Comprehensive (2000-3000 words)")
        print("4. No summary")
        
        while True:
            try:
                choice = input("\nSelect summary type (1-4): ")
                if choice == '4':
                    args.summary = None
                    break
                elif choice.isdigit() and 1 <= int(choice) <= 3:
                    summary_types = ['brief', 'detailed', 'comprehensive']
                    args.summary = summary_types[int(choice) - 1]
                    break
                else:
                    print("Invalid choice. Please select a number between 1 and 4.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    
    print(f"\n{'='*80}")
    print(f"Starting research on: {args.query}")
    if args.summary:
        print(f"Summary type: {args.summary}")
    print(f"{'='*80}\n")
    
    analyzer = D4BLResearchAnalyzer()
    results = analyzer.analyze_topic(args.query, args.summary)
    
    # Print results based on output format
    if args.output == 'full':
        print("\n=== Full Results ===")
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print_results(results)

if __name__ == "__main__":
    main() 