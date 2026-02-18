from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import FirecrawlSearchTool
import json
from typing import List
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

# Import error handling utilities
from d4bl.services.error_handling import retry_with_backoff, safe_execute, ErrorRecoveryStrategy
from d4bl.settings import get_settings
from d4bl.tools import Crawl4AISearchTool, FirecrawlSearchWrapper
from d4bl.llm import get_ollama_llm, reset_ollama_llm
from d4bl.observability import get_langfuse_client

logger = logging.getLogger(__name__)

# Serper.dev API for search query to URL conversion
# Crawl4AI only works with URLs, so we use Serper.dev to convert search queries to URLs
# Serper.dev uses a simple REST API (no package needed)

# Load environment variables from .env if present (best-effort)
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
env_file_loaded = None
if env_path.exists():
    env_loaded = load_dotenv(env_path)
    if env_loaded:
        env_file_loaded = str(env_path)
        print(f"✓ Loaded .env file from: {env_path}")
else:
    env_loaded = False

# Print which environment variables are loaded (without showing full values)
if env_file_loaded:
    print("\n📋 Environment variables loaded from .env")


@CrewBase
class D4Bl():
    """D4Bl crew with enhanced error handling and reliability"""

    agents: List[BaseAgent]
    tasks: List[Task]

    @before_kickoff
    def before_kickoff_function(self, inputs):
        """Ensure output directory exists before running the crew"""
        os.makedirs('output', exist_ok=True)
        print(f"Starting D4BL research crew with inputs: {inputs}")
        
        # Validate inputs
        if not inputs.get("query"):
            raise ValueError("Query is required for research")
        
        # Log input validation
        logger.info(f"Research query validated: {inputs.get('query')[:100]}...")
        return inputs

    # Learn more about YAML configuration files here:
    # Agents: https://docs.crewai.com/concepts/agents#yaml-configuration-recommended
    # Tasks: https://docs.crewai.com/concepts/tasks#yaml-configuration-recommended
    
    # If you would like to add tools to your agents, you can learn more about it here:
    # https://docs.crewai.com/concepts/agents#agent-tools
    @agent
    def researcher(self) -> Agent:
        settings = get_settings()
        provider = settings.crawl_provider

        if provider == "crawl4ai":
            print(f"🔧 Using Crawl4AI at: {settings.crawl4ai_base_url}")
            crawl_tool = Crawl4AISearchTool(
                base_url=settings.crawl4ai_base_url,
                api_key=settings.crawl4ai_api_key,
            )
            tool_wrapped = crawl_tool
        else:
            if not settings.firecrawl_api_key:
                raise ValueError(
                    "FIRECRAWL_API_KEY not found. Set it or use CRAWL_PROVIDER=crawl4ai."
                )

            firecrawl_tool = FirecrawlSearchTool(
                api_key=settings.firecrawl_api_key,
                max_pages=3,
                max_results=5
            )
            tool_wrapped = FirecrawlSearchWrapper(firecrawl_tool=firecrawl_tool)
            print("🔧 Using Firecrawl (cloud) provider")
        
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            tools=[tool_wrapped],
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

    @agent
    def editor(self) -> Agent:
        return Agent(
            config=self.agents_config['editor'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False
        )

    @agent
    def fact_checker(self) -> Agent:
        return Agent(
            config=self.agents_config['fact_checker'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False
        )

    @agent
    def citation_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['citation_agent'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False
        )

    @agent
    def bias_detection_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['bias_detection_agent'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            verbose=True,
            allow_delegation=False
        )

    @agent
    def data_visualization_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['data_visualization_agent'], # type: ignore[index]
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

    @task
    def fact_checker_task(self) -> Task:
        return Task(
            config=self.tasks_config['fact_checker_task'], # type: ignore[index]
        )

    @task
    def citation_task(self) -> Task:
        return Task(
            config=self.tasks_config['citation_task'], # type: ignore[index]
        )

    @task
    def bias_detection_task(self) -> Task:
        return Task(
            config=self.tasks_config['bias_detection_task'], # type: ignore[index]
        )

    @task
    def editor_task(self) -> Task:
        return Task(
            config=self.tasks_config['editor_task'], # type: ignore[index]
            output_file='output/report_edited.md'  # This is the file that will contain the edited report
        )

    @task
    def data_visualization_task(self) -> Task:
        return Task(
            config=self.tasks_config['data_visualization_task'], # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the D4Bl crew"""
        # To learn how to add knowledge sources to your crew, check out the documentation:
        # https://docs.crewai.com/concepts/knowledge#what-is-knowledge
        # Memory documentation: https://docs.crewai.com/en/concepts/memory

        # Configure memory with Ollama embeddings to match LLM provider
        # This enables short-term, long-term, and entity memory for all agents
        # Explicitly configure embedder to use Ollama instead of default OpenAI
        
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        embedder_model = "mxbai-embed-large"
        
        # Construct the embedder configuration
        # CrewAI requires explicit embedder config to avoid defaulting to OpenAI
        # Note: Use "url" pointing to /api/embeddings endpoint, not "base_url"
        embedder_config = {
            "provider": "ollama",
            "config": {
                "model": embedder_model,
                "url": f"{ollama_base_url}/api/embeddings"
            }
        }

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            memory=True,  # Enable basic memory system (short-term, long-term, entity memory)
            embedder=embedder_config,  # Explicitly set Ollama embedder to avoid OpenAI default
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )

