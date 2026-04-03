from __future__ import annotations

import logging
import os
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, before_kickoff, crew, task

from d4bl.agents.tools import Crawl4AISearchTool
from d4bl.agents.tools.crawl_tools.searxng import SearXNGSearchTool
from d4bl.llm import get_llm
from d4bl.settings import get_settings

logger = logging.getLogger(__name__)


@CrewBase
class D4Bl:
    """D4Bl crew with enhanced error handling and reliability"""

    agents: list[BaseAgent]
    tasks: list[Task]

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

    _mapped_tasks = list(AGENT_TASK_MAP.values())
    if len(_mapped_tasks) != len(set(_mapped_tasks)):
        raise RuntimeError("Duplicate task names in AGENT_TASK_MAP")
    if len(TASK_ORDER) != len(set(TASK_ORDER)):
        raise RuntimeError("Duplicate task names in TASK_ORDER")
    if _mapped_tasks != TASK_ORDER:
        raise RuntimeError("AGENT_TASK_MAP values must exactly match TASK_ORDER")

    def __init__(self):
        """Initialize crew with optional agent selection"""
        self.selected_agents: list[str] | None = None

    @before_kickoff
    def before_kickoff_function(self, inputs):
        """Ensure output directory exists before running the crew"""
        os.makedirs("output", exist_ok=True)
        logger.info("Starting D4BL research crew")

        # Validate inputs
        if not inputs.get("query"):
            raise ValueError("Query is required for research")

        # Log input validation
        logger.info("Research query validated (length=%d)", len(inputs.get("query", "")))
        return inputs

    def _make_simple_agent(self, config_key: str, **kwargs: Any) -> Agent:
        """Create a standard agent with common defaults."""
        return Agent(
            config=self.agents_config[config_key],
            llm=get_llm(),
            verbose=True,
            allow_delegation=False,
            **kwargs,
        )

    @agent
    def researcher(self) -> Agent:
        settings = get_settings()

        # Search tool: SearXNG (default) or legacy Serper via Crawl4AI
        if settings.search_provider == "searxng":
            logger.info("Using SearXNG at: %s", settings.searxng_base_url)
            search_tool = SearXNGSearchTool(
                base_url=settings.searxng_base_url,
            )
        else:
            # Legacy Serper path — kept for backward compatibility
            logger.info("Using Crawl4AI with Serper search")
            search_tool = Crawl4AISearchTool(
                base_url=settings.crawl4ai_base_url,
                api_key=settings.crawl4ai_api_key,
            )

        return Agent(
            config=self.agents_config["researcher"],
            llm=get_llm(),
            tools=[search_tool],
            verbose=True,
            allow_delegation=False,
        )

    @agent
    def data_analyst(self) -> Agent:
        return self._make_simple_agent("data_analyst", max_retries=3)

    @agent
    def writer(self) -> Agent:
        return self._make_simple_agent("writer")

    @agent
    def editor(self) -> Agent:
        return self._make_simple_agent("editor")

    @agent
    def fact_checker(self) -> Agent:
        return self._make_simple_agent("fact_checker")

    @agent
    def citation_agent(self) -> Agent:
        return self._make_simple_agent("citation_agent")

    @agent
    def bias_detection_agent(self) -> Agent:
        return self._make_simple_agent("bias_detection_agent")

    @agent
    def data_visualization_agent(self) -> Agent:
        return self._make_simple_agent("data_visualization_agent")

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
        )

    @task
    def analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["analysis_task"],  # type: ignore[index]
        )

    @task
    def writing_task(self) -> Task:
        return Task(
            config=self.tasks_config["writing_task"],  # type: ignore[index]
            output_file="output/report.md",  # This is the file that will contain the final report
        )

    @task
    def fact_checker_task(self) -> Task:
        return Task(
            config=self.tasks_config["fact_checker_task"],  # type: ignore[index]
        )

    @task
    def citation_task(self) -> Task:
        return Task(
            config=self.tasks_config["citation_task"],  # type: ignore[index]
        )

    @task
    def bias_detection_task(self) -> Task:
        return Task(
            config=self.tasks_config["bias_detection_task"],  # type: ignore[index]
        )

    @task
    def editor_task(self) -> Task:
        return Task(
            config=self.tasks_config["editor_task"],  # type: ignore[index]
            output_file="output/report_edited.md",  # This is the file that will contain the edited report
        )

    @task
    def data_visualization_task(self) -> Task:
        return Task(
            config=self.tasks_config["data_visualization_task"],  # type: ignore[index]
        )

    @crew
    def crew(self) -> Crew:
        """Creates the D4Bl crew"""
        settings = get_settings()
        embedder_provider = settings.embedder_provider

        if embedder_provider == "google":
            if not settings.llm_api_key:
                raise ValueError(
                    "Google embedder selected but LLM_API_KEY is not set. "
                    "Please set the LLM_API_KEY environment variable."
                )
            embedder_config = {
                "provider": "google-generativeai",
                "config": {
                    "api_key": settings.llm_api_key,
                    "model_name": "models/gemini-embedding-001",
                },
            }
        else:
            embedder_config = {
                "provider": "ollama",
                "config": {
                    "model_name": "mxbai-embed-large",
                    "url": f"{settings.ollama_base_url}/api/embeddings",
                },
            }

        # Filter agents and tasks if selected_agents is specified
        agents_to_use = self.agents
        tasks_to_use = self.tasks

        if self.selected_agents:
            # Deduplicate while preserving order
            selected = list(dict.fromkeys(self.selected_agents))

            # Validate selected agent names
            valid_agents = set(self.AGENT_TASK_MAP.keys())
            invalid_agents = set(selected) - valid_agents
            if invalid_agents:
                raise ValueError(
                    f"Invalid agent names: {invalid_agents}. "
                    f"Valid agents are: {', '.join(sorted(valid_agents))}"
                )

            agent_methods = {name: getattr(self, name) for name in self.AGENT_TASK_MAP}
            agents_to_use = [
                agent_methods[agent_name]()
                for agent_name in selected
                if agent_name in agent_methods
            ]

            # Build selected task names as a set for O(1) lookup
            selected_task_names = {
                self.AGENT_TASK_MAP[agent_name]
                for agent_name in selected
                if agent_name in self.AGENT_TASK_MAP
            }

            task_methods = {t: getattr(self, t) for t in self.AGENT_TASK_MAP.values()}

            # Iterate TASK_ORDER to preserve deterministic sequential order
            tasks_to_use = [
                task_methods[task_name]()
                for task_name in self.TASK_ORDER
                if task_name in selected_task_names
            ]

            logger.info(
                "Filtered to %s agent(s) and %s task(s): %s",
                len(agents_to_use),
                len(tasks_to_use),
                ", ".join(selected),
            )

        return Crew(
            agents=agents_to_use,
            tasks=tasks_to_use,
            process=Process.sequential,
            verbose=True,
            memory=True,  # Enable basic memory system (short-term, long-term, entity memory)
            embedder=embedder_config,
        )