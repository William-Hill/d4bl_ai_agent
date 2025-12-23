from crewai import Agent, Crew, Process, Task, LLM
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
from d4bl.error_handling import retry_with_backoff, safe_execute, ErrorRecoveryStrategy
from d4bl.settings import get_settings
from d4bl.tools import Crawl4AISearchTool, FirecrawlSearchWrapper

logger = logging.getLogger(__name__)

# Serper.dev API for search query to URL conversion
# Crawl4AI only works with URLs, so we use Serper.dev to convert search queries to URLs
# Serper.dev uses a simple REST API (no package needed)

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

# Configure Langfuse OTLP endpoint EARLY, before any OpenTelemetry imports
# This must be set before OpenInference instrumentation initializes
# Priority: Use environment variable if set (from docker-compose), otherwise compute it

# Get Langfuse host configuration (needed for both paths)
langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3002")
langfuse_otel_host = os.getenv("LANGFUSE_OTEL_HOST")

# If running in Docker, use service name for internal communication
if os.path.exists("/.dockerenv"):
    # Replace localhost with service name if needed
    if "localhost" in langfuse_host:
        langfuse_host = langfuse_host.replace("localhost", "langfuse-web")
    if not langfuse_otel_host:
        # Use port 3000 (internal) not 3002 (external)
        langfuse_otel_host = langfuse_host.replace(":3002", ":3000").replace(":3001", ":3000")

# Check if OTLP endpoint is already set (from docker-compose.yml)
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

if not otlp_endpoint:
    # Compute OTLP endpoint if not already set
    otlp_endpoint = f"{langfuse_otel_host or langfuse_host}/api/public/otel/v1/traces"
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otlp_endpoint
else:
    # Use the existing value, but ensure TRACES_ENDPOINT is also set
    if not os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otlp_endpoint

# Ensure otlp_endpoint is always defined for logging
if not otlp_endpoint:
    otlp_endpoint = f"{langfuse_otel_host or langfuse_host}/api/public/otel/v1/traces"

# Also set LANGFUSE_OTEL_HOST for Langfuse SDK's built-in OTLP exporter
if langfuse_otel_host and not os.getenv("LANGFUSE_OTEL_HOST"):
    os.environ["LANGFUSE_OTEL_HOST"] = langfuse_otel_host
elif not os.getenv("LANGFUSE_OTEL_HOST"):
    os.environ["LANGFUSE_OTEL_HOST"] = langfuse_host

# Debug: Print OTLP configuration (only in Docker or if explicitly enabled)
if os.path.exists("/.dockerenv") or os.getenv("DEBUG_OTLP"):
    print(f"🔧 OTLP Configuration:")
    print(f"   LANGFUSE_HOST: {langfuse_host}")
    print(f"   LANGFUSE_OTEL_HOST: {langfuse_otel_host or langfuse_host}")
    print(f"   OTEL_EXPORTER_OTLP_ENDPOINT: {os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')}")
    print(f"   OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: {os.getenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT')}")
    print()

# Print which environment variables are loaded (without showing full values)
if env_loaded:
    print("\n📋 Environment variables loaded:")
    env_vars_to_check = [
        "FIRECRAWL_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GROQ_API_KEY",
        "OLLAMA_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST"
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

# Initialize Langfuse for observability and tracing
# Reference: https://langfuse.com/integrations/frameworks/crewai
_langfuse_initialized = False
_langfuse_client = None

def initialize_langfuse():
    """Initialize Langfuse observability and CrewAI instrumentation"""
    global _langfuse_initialized, _langfuse_client
    
    if _langfuse_initialized:
        return _langfuse_client
    
    try:
        from langfuse import get_client
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        
        # Get Langfuse configuration from environment
        # OTLP endpoint should already be configured above (before imports)
        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        langfuse_host = os.getenv("LANGFUSE_HOST", "http://localhost:3002")
        langfuse_base_url = os.getenv("LANGFUSE_BASE_URL", langfuse_host)
        langfuse_otel_host = os.getenv("LANGFUSE_OTEL_HOST", langfuse_host)
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", f"{langfuse_otel_host}/api/public/otel/v1/traces")
        
        # If running in Docker, ensure BASE_URL uses service name and internal port
        if os.path.exists("/.dockerenv"):
            # Fix LANGFUSE_BASE_URL if it's using localhost or wrong port
            if "localhost" in langfuse_base_url or ":3002" in langfuse_base_url:
                langfuse_base_url = langfuse_host  # Use the corrected host (langfuse-web:3000)
        
        # Set environment variables if not already set
        if langfuse_public_key and not os.getenv("LANGFUSE_PUBLIC_KEY"):
            os.environ["LANGFUSE_PUBLIC_KEY"] = langfuse_public_key
        if langfuse_secret_key and not os.getenv("LANGFUSE_SECRET_KEY"):
            os.environ["LANGFUSE_SECRET_KEY"] = langfuse_secret_key
        if not os.getenv("LANGFUSE_HOST"):
            os.environ["LANGFUSE_HOST"] = langfuse_host
        # Always set BASE_URL to the corrected value in Docker
        if os.path.exists("/.dockerenv"):
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url
        elif not os.getenv("LANGFUSE_BASE_URL"):
            os.environ["LANGFUSE_BASE_URL"] = langfuse_base_url
        
        # Initialize Langfuse client
        _langfuse_client = get_client()
        
        # Verify connection (non-blocking - don't fail if Langfuse isn't ready yet)
        # The OTLP exporter will still work even if auth check fails
        try:
            if _langfuse_client.auth_check():
                print("✅ Langfuse client authenticated and ready!")
            else:
                print("⚠️ Langfuse authentication failed. Please check your credentials and host.")
                print(f"   LANGFUSE_HOST: {langfuse_host}")
                print(f"   LANGFUSE_BASE_URL: {langfuse_base_url}")
                print("   Continuing anyway - OTLP traces will still be sent when Langfuse is ready.")
        except Exception as auth_error:
            print(f"⚠️ Could not connect to Langfuse for auth check: {auth_error}")
            print(f"   LANGFUSE_HOST: {langfuse_host}")
            print(f"   LANGFUSE_BASE_URL: {langfuse_base_url}")
            print("   This is OK - Langfuse may not be ready yet. OTLP traces will be sent when it's available.")
            # Don't fail - continue with instrumentation
        
        # Initialize CrewAI instrumentation
        # This automatically captures CrewAI operations and exports OpenTelemetry spans to Langfuse
        # The OTLP endpoint is configured above via OTEL_EXPORTER_OTLP_ENDPOINT
        
        # CRITICAL: Verify OTLP endpoint is set correctly before instrumentation
        # The exporter reads this when it's created, so it must be set before instrument() is called
        current_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        current_traces_endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        
        if not current_otlp_endpoint:
            # Force set it if somehow not set
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otlp_endpoint
            print(f"⚠️  OTLP endpoint was not set! Forced to: {otlp_endpoint}")
        else:
            print(f"✓ OTLP endpoint configured: {current_otlp_endpoint}")
            if current_otlp_endpoint != otlp_endpoint:
                print(f"⚠️  WARNING: OTLP endpoint mismatch!")
                print(f"   Expected: {otlp_endpoint}")
                print(f"   Actual: {current_otlp_endpoint}")
        
        # Now instrument - this will create the exporter with the endpoint above
        CrewAIInstrumentor().instrument(skip_dep_check=True)
        print(f"✅ CrewAI instrumentation initialized")
        
        _langfuse_initialized = True
        print(f"✅ CrewAI instrumentation initialized for Langfuse observability")
        print(f"   Langfuse Host: {langfuse_host}")
        print(f"   View traces at: {langfuse_base_url}")
        
        return _langfuse_client
    except ImportError as e:
        print(f"⚠️ Langfuse dependencies not installed: {e}")
        print("   Install with: pip install langfuse openinference-instrumentation-crewai")
        _langfuse_initialized = False
        return None
    except Exception as e:
        print(f"⚠️ Error initializing Langfuse: {e}")
        import traceback
        traceback.print_exc()
        _langfuse_initialized = False
        return None

# Initialize Langfuse on module import
initialize_langfuse()

def get_langfuse_client():
    """Get the initialized Langfuse client, initializing if necessary."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = initialize_langfuse()
    return _langfuse_client

# Configure Ollama LLM with Mistral 7B
# Using direct code configuration as per CrewAI documentation
# Initialize lazily to avoid import-time errors when API server starts
_ollama_llm = None

# Request queue management for Ollama
# Note: Actual request queuing is handled by Ollama server-side
# Client-side we can configure retries and timeouts, but the server manages the queue
# Configure Ollama server-side queue via environment variables when starting Ollama:
# - OLLAMA_MAX_QUEUE: Maximum number of queued requests (default: 512)
# - OLLAMA_NUM_PARALLEL: Max parallel requests per model (default: auto, typically 4 or 1)
# - OLLAMA_MAX_LOADED_MODELS: Max models loaded concurrently (default: 3x GPUs or 3)

def get_ollama_llm():
    """Get or create the Ollama LLM instance (lazy initialization)"""
    global _ollama_llm
    if _ollama_llm is None:
        try:
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            # Ensure base_url doesn't have trailing slash for LiteLLM compatibility
            ollama_base_url = ollama_base_url.rstrip('/')
            
            # Set environment variable for LiteLLM to use
            os.environ["OLLAMA_API_BASE"] = ollama_base_url
            
            # Note: Ollama server-side queue settings can be configured via environment variables:
            # - OLLAMA_MAX_QUEUE: Maximum number of queued requests (default: 512)
            # - OLLAMA_NUM_PARALLEL: Max parallel requests per model (default: auto)
            # - OLLAMA_MAX_LOADED_MODELS: Max models loaded concurrently (default: 3x GPUs or 3)
            # These should be set when starting Ollama, not here.
            
            _ollama_llm = LLM(
                model="ollama/mistral",
                base_url=ollama_base_url,
                temperature=0.5,  # Lower temperature for more focused responses
                timeout=180.0,    # 3 minutes timeout (increased for reliability)
                num_retries=5,    # Increased retries for connection issues
            )
            print(f"✅ Initialized Ollama LLM with base_url: {ollama_base_url}")
            print(f"   Note: Configure Ollama server queue settings (OLLAMA_MAX_QUEUE, OLLAMA_NUM_PARALLEL) when starting Ollama")
        except ImportError as e:
            raise ImportError(
                "LiteLLM is required for Ollama support. "
                "Please install it with: pip install litellm"
            ) from e
        except Exception as e:
            print(f"⚠️ Error initializing Ollama LLM: {e}")
            raise
    return _ollama_llm


def reset_ollama_llm():
    """Reset the Ollama LLM instance (useful for connection issues)"""
    global _ollama_llm
    _ollama_llm = None
    print("🔄 Reset Ollama LLM instance")


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

