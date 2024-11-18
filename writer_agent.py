from crewai import Agent, Task
from typing import Dict, Literal
import json
from datetime import datetime
import re
from config import LLM_LLAMA70B, LLM_OLLAMA3_2
import os

class WriterAgent:
    def __init__(self):
        self.agent = self.create_agent()
        
    def create_agent(self) -> Agent:
        return Agent(
            role='Research Writer',
            goal='Write clear, engaging, and accurate summaries of research findings',
            backstory="""You are an expert writer specializing in data justice and 
            social impact topics. You excel at distilling complex research into 
            clear, compelling narratives while maintaining accuracy and nuance.""",
            llm=LLM_OLLAMA3_2,
            verbose=True,
            allow_delegation=False
        )
    
    def write_summary(
        self, 
        research_results: Dict,
        format_type: Literal['brief', 'detailed', 'comprehensive'] = 'detailed'
    ) -> Dict:
        """Write a summary of the research and analysis results"""
        print(f"\n{'='*30} Starting summary generation {'='*30}")
        
        try:
            # Extract information
            query = research_results.get('query', 'No query provided')
            analysis = research_results.get('analysis', {}).get('analysis', {})
            sources = research_results.get('research', {}).get('sources', [])
            
            print(f"Query: {query}")
            print(f"Analysis keys: {list(analysis.keys())}")
            
            # Get the task object for writing
            task = self._get_writing_prompt(format_type, query, analysis)
            
            # Execute the task
            summary = self.agent.execute_task(task)
            
            # Create bibliography task
            bib_task = self._get_bibliography_prompt(sources)
            bibliography = self.agent.execute_task(bib_task)
            
            # Create the output
            output = {
                "query": query,
                "format_type": format_type,
                "summary": summary,
                "bibliography": bibliography,
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "metadata": {
                    "word_count": len(summary.split()),
                    "format_guidelines": self._get_format_guidelines(format_type)
                }
            }
            
            # Save both JSON and markdown versions
            json_file = self._save_summary_json(output)
            md_file = self._save_summary_markdown(output)
            
            print(f"Summary saved to: {md_file}")
            print(f"JSON data saved to: {json_file}")
            
            return output
            
        except Exception as e:
            print(f"Error in write_summary: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                "error": str(e),
                "query": research_results.get('query', 'No query provided'),
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S")
            }
    
    def _get_writing_prompt(self, format_type: str, query: str, analysis: Dict) -> Task:
        """Generate appropriate writing prompt based on format type"""
        # Extract key points safely with error handling
        try:
            key_points = analysis.get('key_points', [])
            main_themes = analysis.get('main_themes', [])
            recommendations = analysis.get('recommendations', [])
            data_quality = analysis.get('data_quality', {})
        except AttributeError:
            key_points = []
            main_themes = []
            recommendations = []
            data_quality = {}

        # Create and return a Task object
        return Task(
            description=f"""
            Write a {format_type} summary addressing this research question: {query}

            Analysis Results:
            Key Points: {json.dumps(key_points, indent=2)}
            Main Themes: {json.dumps(main_themes, indent=2)}
            Recommendations: {json.dumps(recommendations, indent=2)}
            Data Quality Metrics: {json.dumps(data_quality, indent=2)}

            Guidelines:
            {self._get_format_guidelines(format_type)}
            
            Additional Requirements:
            - Use clear, engaging language
            - Maintain academic rigor and accuracy
            - Address implications for data justice and racial equity
            - Conclude with actionable insights
            - Focus on synthesizing the key points and themes
            """,
            expected_output=f"""A {format_type} summary following the specified format guidelines:
                - Brief: 250-500 words
                - Detailed: 1000-1500 words
                - Comprehensive: 2000-3000 words
            """,
            agent=self.agent
        )
    
    def _get_format_guidelines(self, format_type: str) -> str:
        """Get format-specific guidelines"""
        guidelines = {
            'brief': """
            - Length: 250-500 words
            - Focus on key findings and main implications
            - Include 3-4 main points
            - One paragraph for context, one for findings, one for implications
            """,
            'detailed': """
            - Length: 1000-1500 words
            - Provide thorough analysis of findings
            - Include methodology overview
            - Discuss multiple perspectives
            - Detailed recommendations section
            - Use subheadings for organization
            """,
            'comprehensive': """
            - Length: 2000-3000 words
            - In-depth analysis of all aspects
            - Extensive context and background
            - Detailed methodology section
            - Multiple case studies or examples
            - Thorough discussion of implications
            - Comprehensive recommendations
            - Executive summary
            - Citations and references
            """
        }
        return guidelines[format_type]
    
    def _get_bibliography_prompt(self, sources: list) -> Task:
        """Generate a prompt for creating an annotated bibliography"""
        return Task(
            description=f"""
            Create an annotated bibliography from these sources:
            {json.dumps(sources, indent=2)}
            
            For each source, include:
            1. Full citation
            2. Brief summary (2-3 sentences)
            3. Relevance to the research question
            
            Format in markdown with proper citations.
            """,
            expected_output="Markdown formatted annotated bibliography",
            agent=self.agent
        )
    
    def _save_summary_markdown(self, summary_data: Dict) -> str:
        """Save the summary as a markdown file"""
        # Create reports directory if it doesn't exist
        os.makedirs('reports', exist_ok=True)
        
        timestamp = summary_data["timestamp"]
        query_part = re.sub(r'[^\w\s-]', '', summary_data["query"])
        query_part = re.sub(r'[-\s]+', '_', query_part).lower()[:50]
        format_type = summary_data["format_type"]
        
        filename = f"reports/summary_{format_type}_{query_part}_{timestamp}.md"
        
        # Create markdown content
        md_content = f"""# Research Summary: {summary_data['query']}

## Overview
- **Date:** {datetime.now().strftime("%Y-%m-%d")}
- **Format:** {format_type.title()}
- **Word Count:** {summary_data['metadata']['word_count']}

## Summary
{summary_data['summary']}

## Analysis Details
### Key Points
{self._format_list(summary_data.get('analysis', {}).get('key_points', []))}

### Main Themes
{self._format_list(summary_data.get('analysis', {}).get('main_themes', []))}

### Recommendations
{self._format_list(summary_data.get('analysis', {}).get('recommendations', []))}

## Annotated Bibliography
{summary_data.get('bibliography', 'No bibliography available')}

---
*Generated by D4BL Research Analyzer*
"""
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md_content)
            
        return filename
    
    def _save_summary_json(self, summary_data: Dict) -> str:
        """Save the raw summary data as JSON"""
        os.makedirs('reports', exist_ok=True)
        
        timestamp = summary_data["timestamp"]
        query_part = re.sub(r'[^\w\s-]', '', summary_data["query"])
        query_part = re.sub(r'[-\s]+', '_', query_part).lower()[:50]
        format_type = summary_data["format_type"]
        
        filename = f"reports/data_summary_{format_type}_{query_part}_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
            
        return filename
    
    def _format_list(self, items: list) -> str:
        """Format a list as markdown bullet points"""
        if not items:
            return "*No items available*"
        return '\n'.join(f"- {item}" for item in items)

def main():
    # Example usage
    from d4bl import D4BLResearchAnalyzer
    
    # Get research results
    analyzer = D4BLResearchAnalyzer()
    research_results = analyzer.analyze_topic(
        "How does algorithmic bias affect criminal justice outcomes?"
    )
    
    # Generate summaries
    writer = WriterAgent()
    
    # Generate different types of summaries
    formats = ['brief', 'detailed', 'comprehensive']
    for format_type in formats:
        print(f"\nGenerating {format_type} summary...")
        summary = writer.write_summary(research_results, format_type)
        print(f"\n{format_type.title()} Summary:")
        print(f"Word count: {summary['metadata']['word_count']}")
        print(summary['summary'][:300] + "...")  # Preview first 300 chars
        print(f"Full summary saved to: {summary['metadata']['filename']}")

if __name__ == "__main__":
    main() 