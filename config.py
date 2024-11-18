import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_community.chat_models import ChatOllama

# Load environment variables
load_dotenv()

# Retrieve the GROQ_API_KEY from the environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# LLM instances
# Llama 3 70B: A large language model with 70 billion parameters, offering high performance and versatility
LLM_LLAMA70B = ChatGroq(model_name="llama3-70b-8192")

# Llama 3 8B: A smaller version of Llama 3 with 8 billion parameters, balancing performance and efficiency
LLM_LLAMA8B = ChatGroq(model_name="llama3-8b-8192")

# Gemma 2 9B: Google's 9 billion parameter model, known for its efficiency and strong performance on various tasks
LLM_GEMMA2 = ChatGroq(model_name="gemma2-9b-it")

# Mixtral 8x7B: A mixture of experts model with 8 expert sub-models, each with 7 billion parameters,
# offering strong performance across a wide range of tasks
LLM_MIXTRAL = ChatGroq(model_name="mixtral-8x7b-32768")

# Ollama with more robust settings
LLM_OLLAMA3_1 = ChatOllama(
    model='llama3.1',
    timeout=120.0,  # Increase timeout to 120 seconds
    temperature=0.5,  # Lower temperature for faster, more focused responses
    streaming=True,
    base_url="http://localhost:11434",  # Explicitly set base URL
    retry_on_failure=True,  # Enable retries
    num_retries=3
)

LLM_OLLAMA3_2 = ChatOllama(
    model='llama3.2',
    timeout=120.0,  # Increase timeout to 120 seconds
    temperature=0.5,
    streaming=True,
    base_url="http://localhost:11434",
    retry_on_failure=True,
    num_retries=3
)
