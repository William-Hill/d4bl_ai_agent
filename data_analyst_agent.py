import re
from crewai import Agent, Task
from typing import Dict, Any
import json
from datetime import datetime
import traceback
from config import LLM_LLAMA70B, LLM_OLLAMA3_2
import asyncio
from concurrent.futures import TimeoutError

class DataAnalystAgent:
    def __init__(self):
        try:
            # Set a timeout for LLM operations
            self.timeout = 30  # 30 seconds timeout
            self.agent = self.create_agent()
            print("DataAnalystAgent initialized successfully")
        except Exception as e:
            print(f"Error initializing DataAnalystAgent: {str(e)}")
            traceback.print_exc()
            raise
        
    def create_agent(self) -> Agent:
        try:
            agent = Agent(
                role='Data Analyst',
                goal='Analyze and extract insights from research data',
                backstory="""You are an expert data analyst specializing in 
                processing research data. You excel at identifying patterns 
                and extracting meaningful insights.""",
                llm=LLM_OLLAMA3_2,
                verbose=True,
                allow_delegation=False
            )
            print("Agent created successfully")
            return agent
        except Exception as e:
            print(f"Error creating agent: {str(e)}")
            traceback.print_exc()
            raise
    
    def analyze_research_results(self, research_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze and clean the research results"""
        print("\n" + "="*80)
        print("STARTING RESEARCH ANALYSIS")
        print("="*80)
        
        print("\nInput Data:")
        print(f"- Type: {type(research_results)}")
        print(f"- Keys: {list(research_results.keys())}")
        
        try:
            results_text = research_results.get('results', '')
            print(f"\nText to Analyze:")
            print(f"- Length: {len(results_text)} characters")
            print(f"- Preview: {results_text[:200]}...")
            
            analysis = {"analysis": {}}
            
            # Execute each analysis step with detailed logging
            steps = [
                ("Key Points", self._extract_key_points),
                ("Themes", self._identify_themes),
                ("Data Quality", self._assess_data_quality),
            ]
            
            for step_name, step_func in steps:
                print(f"\n{'='*30} {step_name} {'='*30}")
                try:
                    result = step_func(results_text)
                    analysis["analysis"][step_name.lower().replace(" ", "_")] = result
                    print(f"\n{step_name} completed successfully")
                except Exception as e:
                    print(f"Error in {step_name}: {str(e)}")
                    analysis["analysis"][step_name.lower().replace(" ", "_")] = []
            
            # Generate recommendations last
            print("\n" + "="*30 + " Recommendations " + "="*30)
            try:
                recommendations = self._generate_recommendations(
                    analysis["analysis"]["key_points"],
                    analysis["analysis"]["themes"]
                )
                analysis["analysis"]["recommendations"] = recommendations
                print("\nRecommendations generated successfully")
            except Exception as e:
                print(f"Error generating recommendations: {str(e)}")
                analysis["analysis"]["recommendations"] = []
            
            print("\n" + "="*80)
            print("ANALYSIS COMPLETE")
            print("="*80)
            
            return analysis
            
        except Exception as e:
            print(f"\nERROR IN ANALYSIS: {str(e)}")
            traceback.print_exc()
            return {
                "analysis": {
                    "error": f"{str(e)}\n{traceback.format_exc()}"
                }
            }
    
    def _execute_task_with_timeout(self, task: Task, task_name: str) -> Any:
        """Execute a task with timeout and detailed logging"""
        print(f"\n{'='*50}")
        print(f"Starting {task_name}")
        print(f"{'='*50}")
        
        try:
            # Set timeout for task execution
            result = self.agent.execute_task(task)
            print(f"\nTask Result for {task_name}:")
            print(f"{'='*30}")
            print(result)
            print(f"{'='*30}")
            return result
            
        except TimeoutError:
            print(f"\nTimeout executing {task_name} after {self.timeout} seconds")
            raise
        except Exception as e:
            print(f"\nError executing {task_name}: {str(e)}")
            traceback.print_exc()
            raise
    
    def _extract_key_points(self, text: str) -> list:
        """Extract main points from the research text"""
        try:
            # Handle text input type
            if isinstance(text, list):
                text = ' '.join(str(item) for item in text)
            elif not isinstance(text, str):
                text = str(text)
            
            # Limit text length to prevent LLM overload
            max_text_length = 4000
            truncated_text = text[:max_text_length]
            if len(text) > max_text_length:
                truncated_text += "..."
            
            task = Task(
                description=f"""
                Extract 3-5 key points from this research text. 
                Be concise and focus on the most important findings:
                
                {truncated_text}
                """,
                expected_output="A list of key points, one per line",
                agent=self.agent
            )
            
            result = self._execute_task_with_timeout(task, "Key Points Extraction")
            
            # Handle different result types
            if isinstance(result, list):
                points = result
            elif isinstance(result, str):
                # Split string on newlines and filter out empty lines
                points = [point.strip() for point in result.split('\n') if point.strip()]
            else:
                raise ValueError(f"Unexpected result type: {type(result)}")
            
            print(f"\nExtracted {len(points)} key points")
            for i, point in enumerate(points, 1):
                print(f"{i}. {point}")
            return points
            
        except Exception as e:
            print(f"Error in _extract_key_points: {str(e)}")
            traceback.print_exc()
            raise  # Re-raise the exception
    
    def _identify_themes(self, text: str) -> list:
        """Identify main themes in the research"""
        try:
            # Handle text input type
            if isinstance(text, list):
                text = ' '.join(str(item) for item in text)
            elif not isinstance(text, str):
                text = str(text)
            
            # Limit text length
            max_text_length = 4000
            truncated_text = text[:max_text_length]
            if len(text) > max_text_length:
                truncated_text += "..."
            
            task = Task(
                description=f"""
                Identify 2-3 main themes from this text:
                
                {truncated_text}
                """,
                expected_output="A list of main themes, one per line",
                agent=self.agent
            )
            
            result = self._execute_task_with_timeout(task, "Theme Identification")
            
            # Handle different result types
            if isinstance(result, list):
                themes = result
            elif isinstance(result, str):
                # Fixed: Changed 'theme' to 'result' in the split operation
                themes = [theme.strip() for theme in result.split('\n') if theme.strip()]
            else:
                raise ValueError(f"Unexpected result type: {type(result)}")
            
            print(f"Themes identified: {len(themes)}")
            for i, theme in enumerate(themes, 1):
                print(f"{i}. {theme}")
            return themes
            
        except Exception as e:
            print(f"Error in _identify_themes: {str(e)}")
            traceback.print_exc()
            raise  # Re-raise the exception
    
    def _assess_data_quality(self, text: str) -> Dict[str, Any]:
        """Assess the quality of the research data"""
        try:
            # Ensure text is a string
            if isinstance(text, list):
                text = ' '.join(str(item) for item in text)
            elif not isinstance(text, str):
                text = str(text)
            
            return {
                "completeness": self._calculate_completeness(text),
                "relevance": self._assess_relevance(text),
                "reliability": self._assess_reliability(text)
            }
        except Exception as e:
            print(f"Error in _assess_data_quality: {str(e)}")
            traceback.print_exc()
            return {
                "completeness": 0.0,
                "relevance": 0.0,
                "reliability": 0.0
            }
    
    def _calculate_completeness(self, text: str) -> float:
        """Calculate a completeness score"""
        try:
            # Ensure text is a string
            if isinstance(text, list):
                text = ' '.join(str(item) for item in text)
            elif not isinstance(text, str):
                text = str(text)
            
            # Calculate completeness
            words = len(text.split())
            return min(1.0, words / 1000)  # Normalize to 0-1
        except Exception as e:
            print(f"Error calculating completeness: {str(e)}")
            traceback.print_exc()
            return 0.0
    
    def _assess_relevance(self, text: str) -> float:
        """Assess relevance of the content"""
        try:
            task = Task(
                description=f"""
                On a scale of 0 to 1, assess how relevant this content is to the research query.
                
                Text to analyze:
                {text[:1000]}...
                
                Requirements:
                - Return ONLY a number between 0 and 1
                - Do not include any other text or explanation
                - Examples of valid responses: "0.8" or "0.45" or "1.0"
                
                Consider:
                - Direct relevance to the topic
                - Currency of information
                - Depth of coverage
                """,
                expected_output="A single float between 0 and 1 (e.g., '0.8')",
                agent=self.agent
            )
            
            result = self._execute_task_with_timeout(task, "Relevance Assessment")
            
            # Clean the result to extract just the number
            cleaned_result = result.strip()
            # Remove any non-numeric characters except decimal point
            cleaned_result = ''.join(c for c in cleaned_result if c.isdigit() or c == '.')
            
            try:
                relevance = float(cleaned_result)
                # Ensure the value is between 0 and 1
                relevance = max(0.0, min(1.0, relevance))
                print(f"Relevance score: {relevance}")
                return relevance
            except ValueError:
                print(f"Could not convert result to float: {cleaned_result}")
                return 0.0
            
        except Exception as e:
            print(f"Error assessing relevance: {str(e)}")
            traceback.print_exc()
            return 0.0
    
    def _assess_reliability(self, text: str) -> float:
        """Assess reliability of the content"""
        try:
            task = Task(
                description=f"""
                Assess the reliability of this content on a scale of 0 to 1.
                
                Text to analyze:
                {text[:1000]}...
                
                Requirements:
                - Return ONLY a number between 0 and 1
                - Do not include any other text or explanation
                - Examples of valid responses: "0.8" or "0.45" or "1.0"
                
                Consider:
                - Source credibility
                - Data backing
                - Consistency
                """,
                expected_output="A single float between 0 and 1 (e.g., '0.8')",
                agent=self.agent
            )
            
            result = self._execute_task_with_timeout(task, "Reliability Assessment")
            
            # Clean the result to extract just the number
            cleaned_result = result.strip()
            # Remove any non-numeric characters except decimal point
            cleaned_result = ''.join(c for c in cleaned_result if c.isdigit() or c == '.')
            
            try:
                reliability = float(cleaned_result)
                # Ensure the value is between 0 and 1
                reliability = max(0.0, min(1.0, reliability))
                print(f"Reliability score: {reliability}")
                return reliability
            except ValueError:
                print(f"Could not convert result to float: {cleaned_result}")
                return 0.0
            
        except Exception as e:
            print(f"Error assessing reliability: {str(e)}")
            traceback.print_exc()
            return 0.0
    
    def _generate_recommendations(self, key_points: list, themes: list) -> list:
        """Generate recommendations based on analysis"""
        print("Creating recommendations task...")
        try:
            task = Task(
                description=f"""
                Based on these key points and themes, generate actionable recommendations:
                
                Key Points:
                {json.dumps(key_points, indent=2)}
                
                Themes:
                {json.dumps(themes, indent=2)}
                
                List each recommendation on a new line.
                Be specific and actionable.
                Focus on practical steps that can be taken.
                Prioritize recommendations that address data justice and social impact.
                """,
                expected_output="A list of specific recommendations, one per line",
                agent=self.agent
            )
            
            print("Executing recommendations task...")
            recommendations = self.agent.execute_task(task)
            print(f"Recommendations generated: {len(recommendations.split('\n'))} found")
            return recommendations.split('\n')
        except Exception as e:
            print(f"Error in _generate_recommendations: {str(e)}")
            traceback.print_exc()
            return []
    
    def _save_analysis(self, analysis: Dict[str, Any]) -> None:
        """Save the analysis results to a file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_part = re.sub(r'[^\w\s-]', '', analysis["original_query"])
        query_part = re.sub(r'[-\s]+', '_', query_part).lower()[:50]
        filename = f"analysis_results_{query_part}_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)

def main():
    # Example usage
    from research_agent import ResearchAgent
    
    # Get research results
    research_agent = ResearchAgent()
    research_results = research_agent.research(
        "What are the environmental impacts of electric vehicles?"
    )
    
    # Analyze results
    analyst = DataAnalystAgent()
    analysis = analyst.analyze_research_results(research_results)
    
    # Print analysis
    print("\n=== Analysis Results ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main() 