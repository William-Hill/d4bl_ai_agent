from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import FirecrawlSearchTool
from typing import List
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from multiple possible locations
# File is at: src/d4bl/crew.py
# So we need to go up 2 levels to get to project root
project_root = Path(__file__).parent.parent.parent  # Go up to project root

env_path = project_root / '.env'

# Try loading .env from project root
env_file_loaded = None
if env_path.exists():
    env_loaded = load_dotenv(env_path)
    if env_loaded:
        env_file_loaded = str(env_path)
        print(f"✓ Loaded .env file from: {env_path}")
else:
    env_loaded = False
    print("⚠ Warning: No .env file found. Please create a .env file with your API keys.")
    print(f"  Checked location: {env_path}")

# Set default Ollama base URL if not set
if not os.getenv("OLLAMA_BASE_URL"):
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

# Print which environment variables are loaded (without showing full values)
if env_loaded:
    print("\n📋 Environment variables loaded:")
    env_vars_to_check = [
        "FIRECRAWL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "OLLAMA_BASE_URL"
    ]
    for var in env_vars_to_check:
        value = os.getenv(var)
        if value:
            # Show first 8 chars and last 4 chars for security, or just "***" if too short
            if len(value) > 12:
                masked = f"{value[:4]}...{value[-4:]}"
            else:
                masked = "***"
            print(f"  ✓ {var}: {masked} (loaded)")
        else:
            print(f"  ✗ {var}: not set")
    print()
    
# Print LLM configuration
print("🤖 LLM Configuration:")
print("  Using Ollama with Mistral 7B")
print(f"  Ollama Base URL: {os.getenv('OLLAMA_BASE_URL')}")
print()

# Configure Ollama LLM with Mistral 7B
# Using direct code configuration as per CrewAI documentation
# Initialize lazily to avoid import-time errors when API server starts
_ollama_llm = None

def get_ollama_llm():
    """Get or create the Ollama LLM instance (lazy initialization)"""
    global _ollama_llm
    if _ollama_llm is None:
        try:
            _ollama_llm = LLM(
                model="ollama/mistral",
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=0.5,  # Lower temperature for more focused responses
                timeout=120.0,    # 2 minutes timeout
            )
        except ImportError as e:
            raise ImportError(
                "LiteLLM is required for Ollama support. "
                "Please install it with: pip install litellm"
            ) from e
    return _ollama_llm

# If you want to run a snippet of code before or after the crew starts,
# you can use the @before_kickoff and @after_kickoff decorators
# https://docs.crewai.com/concepts/crews#example-crew-class-with-decorators

@CrewBase
class D4Bl():
    """D4Bl crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    @before_kickoff
    def before_kickoff_function(self, inputs):
        """Ensure output directory exists before running the crew"""
        os.makedirs('output', exist_ok=True)
        print(f"Starting D4BL research crew with inputs: {inputs}")
        return inputs

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def researcher(self) -> Agent:
        firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
        if not firecrawl_api_key:
            raise ValueError(
                "FIRECRAWL_API_KEY not found in environment variables. "
                "Please create a .env file in the project root "
                "with: FIRECRAWL_API_KEY=your_api_key_here"
            )
        
        firecrawl_tool = FirecrawlSearchTool(
            api_key=firecrawl_api_key,
            max_pages=3,  # Limit to 3 pages
            max_results=5  # Limit to 5 results per page
        )
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            tools=[firecrawl_tool],
            verbose=True,
            allow_delegation=False
        )

    @agent
    def data_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['data_analyst'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False,
            max_retries=3
        )

    @agent
    def writer(self) -> Agent:
        return Agent(
            config=self.agents_config['writer'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False
        )

    # To learn more about structured task outputs,
    # task dependencies, and task callbacks, check out the documentation:
    # https://docs.crewai.com/concepts/tasks#overview-of-a-task
    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config['research_task'], # type: ignore[index]
        )

    @task
    def analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config['analysis_task'], # type: ignore[index]
        )

    @task
    def writing_task(self) -> Task:
        return Task(
            config=self.tasks_config['writing_task'], # type: ignore[index]
            output_file='output/report.md'  # This is the file that will contain the final report
        )

    @crew
    def crew(self) -> Crew:
        """Creates the D4Bl crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )

