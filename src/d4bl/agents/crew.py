from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import FirecrawlSearchTool
from typing import List, Optional
import os
import logging

from d4bl.settings import get_settings
from d4bl.agents.tools import (
    Crawl4AISearchTool,
    FirecrawlSearchWrapper,
    SelfHostedFirecrawlSearchTool,
)
from d4bl.llm import get_ollama_llm

logger = logging.getLogger(__name__)


@CrewBase
class D4Bl():
    """D4Bl crew with enhanced error handling and reliability"""

    agents: List[BaseAgent]
    tasks: List[Task]
    
    # Agent to task mapping
    AGENT_TASK_MAP = {
        "researcher": "research_task",
        "data_analyst": "analysis_task",
        "writer": "writing_task",
        "fact_checker": "fact_checker_task",
        "citation_agent": "citation_task",
        "bias_detection_agent": "bias_detection_task",
        "editor": "editor_task",
        "data_visualization_agent": "data_visualization_task",
    }

    TASK_ORDER = [
        "research_task",
        "analysis_task",
        "writing_task",
        "fact_checker_task",
        "citation_task",
        "bias_detection_task",
        "editor_task",
        "data_visualization_task",
    ]
    
    def __init__(self):
        """Initialize crew with optional agent selection"""
        self.selected_agents: Optional[List[str]] = None

    @before_kickoff
    def before_kickoff_function(self, inputs):
        """Ensure output directory exists before running the crew"""
        os.makedirs('output', exist_ok=True)
        logger.info("Starting D4BL research crew with inputs: %s", inputs)
        
        # Validate inputs
        if not inputs.get("query"):
            raise ValueError("Query is required for research")
        
        # Log input validation
        logger.info(f"Research query validated: {inputs.get('query')[:100]}...")
        return inputs

    @agent
    def researcher(self) -> Agent:
        settings = get_settings()
        provider = settings.crawl_provider

        if provider == "crawl4ai":
            logger.info("Using Crawl4AI at: %s", settings.crawl4ai_base_url)
            crawl_tool = Crawl4AISearchTool(
                base_url=settings.crawl4ai_base_url,
                api_key=settings.crawl4ai_api_key,
            )
        elif settings.firecrawl_base_url:
            logger.info(
                "Using Firecrawl (self-hosted) at: %s",
                settings.firecrawl_base_url,
            )
            crawl_tool = FirecrawlSearchWrapper(
                firecrawl_tool=SelfHostedFirecrawlSearchTool(
                    base_url=settings.firecrawl_base_url,
                    api_key=settings.firecrawl_api_key,
                    max_pages=3,
                    max_results=5,
                )
            )
        else:
            if not settings.firecrawl_api_key:
                raise ValueError(
                    "FIRECRAWL_API_KEY not found. Set it or use CRAWL_PROVIDER=crawl4ai "
                    "or set FIRECRAWL_BASE_URL for self-hosted."
                )
            crawl_tool = FirecrawlSearchWrapper(
                firecrawl_tool=FirecrawlSearchTool(
                    api_key=settings.firecrawl_api_key,
                    max_pages=3,
                    max_results=5,
                )
            )
            logger.info("Using Firecrawl (cloud) provider")

        return Agent(
            config=self.agents_config['researcher'],
            llm=get_ollama_llm(),
            tools=[crawl_tool],
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
        ollama_base_url = get_settings().ollama_base_url
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

        # Filter agents and tasks if selected_agents is specified
        agents_to_use = self.agents
        tasks_to_use = self.tasks
        
        if self.selected_agents:
            # Validate selected agent names
            valid_agents = set(self.AGENT_TASK_MAP.keys())
            selected_set = set(self.selected_agents)
            invalid_agents = selected_set - valid_agents
            if invalid_agents:
                raise ValueError(
                    f"Invalid agent names: {invalid_agents}. "
                    f"Valid agents are: {', '.join(sorted(valid_agents))}"
                )
            
            # Get agent method names that match selected_agents
            agent_methods = {
                'researcher': self.researcher,
                'data_analyst': self.data_analyst,
                'writer': self.writer,
                'fact_checker': self.fact_checker,
                'citation_agent': self.citation_agent,
                'bias_detection_agent': self.bias_detection_agent,
                'editor': self.editor,
                'data_visualization_agent': self.data_visualization_agent,
            }
            agents_to_use = [
                agent_methods[agent_name]()
                for agent_name in self.selected_agents
                if agent_name in agent_methods
            ]
            
            # Build selected task names as a set for O(1) lookup
            selected_task_names = {
                self.AGENT_TASK_MAP[agent_name]
                for agent_name in self.selected_agents
                if agent_name in self.AGENT_TASK_MAP
            }

            # Get task method names
            task_methods = {
                'research_task': self.research_task,
                'analysis_task': self.analysis_task,
                'writing_task': self.writing_task,
                'fact_checker_task': self.fact_checker_task,
                'citation_task': self.citation_task,
                'bias_detection_task': self.bias_detection_task,
                'editor_task': self.editor_task,
                'data_visualization_task': self.data_visualization_task,
            }

            # Iterate TASK_ORDER to preserve deterministic sequential order
            tasks_to_use = [
                task_methods[task_name]()
                for task_name in self.TASK_ORDER
                if task_name in selected_task_names and task_name in task_methods
            ]
            
            logger.info(
                f"Filtered to {len(agents_to_use)} agent(s) and {len(tasks_to_use)} task(s): "
                f"{', '.join(self.selected_agents)}"
            )

        return Crew(
            agents=agents_to_use,
            tasks=tasks_to_use,
            process=Process.sequential,
            verbose=True,
            memory=True,  # Enable basic memory system (short-term, long-term, entity memory)
            embedder=embedder_config,
        )

