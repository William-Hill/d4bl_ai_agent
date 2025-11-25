from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task, before_kickoff
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai_tools import FirecrawlSearchTool
from crewai.tools import BaseTool
from pydantic import BaseModel, Field, field_validator
from typing import List, Type, Union
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

# Initialize Langfuse for observability
_langfuse_client = None
_langfuse_instrumented = False

def initialize_langfuse():
    """Initialize Langfuse client and CrewAI instrumentation"""
    global _langfuse_client, _langfuse_instrumented
    
    if _langfuse_instrumented:
        return _langfuse_client
    
    try:
        from langfuse import get_client
        from openinference.instrumentation.crewai import CrewAIInstrumentor
        
        # Get Langfuse configuration from environment
        langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
        langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY")
        langfuse_host = os.getenv("LANGFUSE_HOST") or os.getenv("LANGFUSE_BASE_URL") or "http://localhost:3000"
        
        # Only initialize if keys are provided
        if langfuse_public_key and langfuse_secret_key:
            # Set OpenTelemetry exporter endpoint for traces (used by CrewAI instrumentation)
            # This must be set before instrumenting
            otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            if not otel_endpoint:
                # Construct the OTLP endpoint from Langfuse host
                otel_endpoint = f"{langfuse_host}/api/public/otel/v1/traces"
                os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otel_endpoint
                os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = otel_endpoint
            
            # Set authentication headers for OTLP exporter
            # Format: "Authorization=Basic <base64(public_key:secret_key)>"
            # CRITICAL: Must be set BEFORE any OpenTelemetry initialization
            import base64
            credentials = f"{langfuse_public_key}:{langfuse_secret_key}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            otel_headers = f"Authorization=Basic {encoded_credentials}"
            
            # Always set headers to ensure they're available before OpenTelemetry initializes
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = otel_headers
            print(f"   OTLP Headers: Authorization=Basic {encoded_credentials[:20]}...")
            
            # Configure OpenTelemetry SDK programmatically to ensure headers are used
            # The OpenInference instrumentation will use the existing TracerProvider if configured
            # This ensures the exporter has authentication before instrumentation runs
            try:
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry import trace
                
                # Check if TracerProvider is already configured
                current_provider = trace.get_tracer_provider()
                if isinstance(current_provider, TracerProvider):
                    # Provider exists, add our exporter to it
                    otlp_exporter = OTLPSpanExporter(
                        endpoint=otel_endpoint,
                        headers={"Authorization": f"Basic {encoded_credentials}"}
                    )
                    current_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                    print(f"   ✅ Added OTLP exporter with authentication to existing TracerProvider")
                else:
                    # Create a new TracerProvider
                    provider = TracerProvider()
                    
                    # Create OTLP exporter with authentication
                    otlp_exporter = OTLPSpanExporter(
                        endpoint=otel_endpoint,
                        headers={"Authorization": f"Basic {encoded_credentials}"}
                    )
                    
                    # Add batch span processor
                    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                    
                    # Set as global provider
                    trace.set_tracer_provider(provider)
                    print(f"   ✅ OpenTelemetry TracerProvider configured with authentication")
            except Exception as otel_error:
                print(f"   ⚠️ Could not configure OpenTelemetry programmatically: {otel_error}")
                print(f"   Will rely on environment variables - instrumentation should pick them up")
            
            # Initialize Langfuse client
            _langfuse_client = get_client()
            
            # Verify connection (optional - instrumentation will still work even if this fails)
            try:
                if _langfuse_client.auth_check():
                    print("✅ Langfuse client authenticated and ready!")
                else:
                    print("⚠️ Langfuse authentication check failed, but instrumentation will continue.")
                    print("   Traces will be sent via OpenTelemetry exporter.")
            except Exception as auth_error:
                print(f"⚠️ Langfuse authentication check failed: {auth_error}")
                print("   This is non-fatal - instrumentation will continue and traces will be sent via OpenTelemetry.")
            
            # Initialize CrewAI instrumentation
            # This will work even if auth_check failed, as it uses OpenTelemetry exporter
            # IMPORTANT: Headers must be set before instrumentation
            CrewAIInstrumentor().instrument(skip_dep_check=True)
            _langfuse_instrumented = True
            print(f"✅ CrewAI instrumentation initialized for Langfuse observability")
            print(f"   Langfuse Host: {langfuse_host}")
            print(f"   OTLP Endpoint: {otel_endpoint}")
            print(f"   OTLP Headers set: {bool(os.getenv('OTEL_EXPORTER_OTLP_HEADERS'))}")
            
            # Verify OpenTelemetry configuration
            try:
                from opentelemetry import trace
                from opentelemetry.sdk.trace import TracerProvider
                provider = trace.get_tracer_provider()
                if isinstance(provider, TracerProvider):
                    print(f"   OpenTelemetry TracerProvider configured")
                else:
                    print(f"   ⚠️ OpenTelemetry TracerProvider type: {type(provider)}")
            except Exception as e:
                print(f"   ⚠️ Could not verify OpenTelemetry configuration: {e}")
        else:
            print("⚠️ Langfuse keys not found. Skipping Langfuse initialization.")
            print("   Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable observability.")
            _langfuse_client = None
    except ImportError as e:
        print(f"⚠️ Langfuse dependencies not installed: {e}")
        print("   Install with: pip install langfuse openinference-instrumentation-crewai")
        _langfuse_client = None
    except Exception as e:
        print(f"⚠️ Error initializing Langfuse: {e}")
        _langfuse_client = None
    
    return _langfuse_client

def get_langfuse_client():
    """Get the Langfuse client instance"""
    if _langfuse_client is None:
        initialize_langfuse()
    return _langfuse_client

# Initialize Langfuse on module import
initialize_langfuse()

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


class FirecrawlSearchWrapperInput(BaseModel):
    """Input schema for Firecrawl Search Wrapper tool."""
    query: Union[str, dict] = Field(..., description="The search query as a plain text string. Example: 'data science trends 2025'")
    
    @field_validator('query', mode='before')
    @classmethod
    def normalize_query(cls, v):
        """Normalize input - handle both strings and dicts from Ollama."""
        if isinstance(v, dict):
            # Extract the actual query value from various possible dict formats
            if 'query' in v:
                return v['query']
            elif 'description' in v:
                # Sometimes Ollama passes the description field as the value
                desc = v['description']
                # If description contains the actual query, use it
                if isinstance(desc, str) and len(desc) > 5:
                    return desc
            elif 'value' in v:
                return v['value']
            else:
                # Try to get the first string value that looks like a query
                for key, value in v.items():
                    if isinstance(value, str) and len(value) > 5:
                        return value
                # Last resort: convert dict to string
                return str(v)
        elif isinstance(v, str):
            return v
        else:
            return str(v)


class FirecrawlSearchWrapper(BaseTool):
    """Wrapper tool for FirecrawlSearchTool that normalizes input format for Ollama compatibility."""
    name: str = "Firecrawl web search tool"
    description: str = (
        "Search webpages using Firecrawl and return the results. "
        "Pass the search query as a plain text string. "
        "Example: Use 'data science trends 2025' not a dictionary or schema."
    )
    args_schema: Type[BaseModel] = FirecrawlSearchWrapperInput
    
    def __init__(self, firecrawl_tool: FirecrawlSearchTool):
        super().__init__()
        # Use object.__setattr__ to bypass Pydantic's validation for internal attributes
        object.__setattr__(self, '_firecrawl_tool', firecrawl_tool)
    
    def _run(self, query: str) -> str:
        """Execute the search with normalized input."""
        # Ensure query is a string (should already be normalized by schema)
        if not isinstance(query, str):
            query = str(query)
        
        # Call the actual Firecrawl tool
        return self._firecrawl_tool._run(query=query)

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
        
        # Create the base Firecrawl tool
        firecrawl_tool = FirecrawlSearchTool(
            api_key=firecrawl_api_key,
            max_pages=3,  # Limit to 3 pages
            max_results=5  # Limit to 5 results per page
        )
        
        # Wrap it to handle Ollama's function calling format issues
        firecrawl_wrapper = FirecrawlSearchWrapper(firecrawl_tool=firecrawl_tool)
        
        return Agent(
            config=self.agents_config['researcher'], # type: ignore[index]
            llm=get_ollama_llm(),  # Use Ollama LLM configured above
            tools=[firecrawl_wrapper],
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

