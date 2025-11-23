# D4BL Research and Analysis Tool

This tool combines web research, data analysis, and writing capabilities to investigate topics related to Data for Black Lives (D4BL). It uses AI agents to gather information, analyze data, generate insights, and create written summaries about data justice and racial equity issues.

## Setup

### Prerequisites

**Python Version Requirements**

This project requires `Python >=3.10 and <3.14`. Check your version:

```bash
python3 --version
```

**Installing a Compatible Python Version**

We recommend using `pyenv` for clean Python version management. This project includes a `.python-version` file that automatically sets the correct Python version.

**Recommended: Using pyenv (macOS/Linux)**

1. **Install pyenv:**
   ```bash
   # macOS
   brew install pyenv
   
   # Linux (Ubuntu/Debian)
   curl https://pyenv.run | bash
   ```

2. **Add pyenv to your shell:**
   ```bash
   # Add to ~/.zshrc (or ~/.bashrc on Linux)
   echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
   echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
   echo 'eval "$(pyenv init -)"' >> ~/.zshrc
   
   # Reload your shell
   source ~/.zshrc
   ```

3. **Install Python 3.13.9:**
   ```bash
   pyenv install 3.13.9
   ```

4. **Set the local version for this project:**
   ```bash
   cd /path/to/d4bl_ai_agent
   pyenv local 3.13.9
   ```

   This creates a `.python-version` file that pyenv will automatically use when you're in this directory.

5. **Verify:**
   ```bash
   python --version  # Should show Python 3.13.9
   ```

**Alternative: Direct Installation (macOS)**

If you prefer not to use pyenv:

```bash
# Install Python 3.13 via Homebrew
brew install python@3.13

# Verify installation
python3.13 --version
```

**Alternative: Direct Installation (Linux)**

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-pip
```

**Alternative: Direct Installation (Windows)**

Download Python 3.13 from [python.org/downloads](https://python.org/downloads) or use the Microsoft Store.

### Installation

CrewAI now uses `uv` as its dependency management tool. Follow these steps to set up the project:

#### Step 1: Install uv (if not already installed)

**On macOS/Linux:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

If your system doesn't have `curl`, you can use `wget`:

```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```

**On Windows:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

If you encounter a `PATH` warning, run:

```bash
uv tool update-shell
```

For more information, refer to [UV's installation guide](https://docs.astral.sh/uv/getting-started/installation/).

#### Step 2: Install Project Dependencies

**If using pyenv (recommended):**

The project's `.python-version` file ensures you're using the correct Python version. Simply:

```bash
# Make sure pyenv is initialized in your shell
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# Verify you're using Python 3.13.9
python --version

# Install dependencies with uv
uv pip install -r requirements.txt

# Or with pip
pip install -r requirements.txt
```

**If not using pyenv:**

Install the required dependencies using `uv`:

```bash
# Specify Python 3.13 explicitly
uv pip install -r requirements.txt --python python3.13

# Or if your default python3 is compatible (3.10-3.13)
uv pip install -r requirements.txt
```

Alternatively, if you prefer using traditional `pip` with a virtual environment:

```bash
# Create a virtual environment with Python 3.13
python3.13 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

**Note:** CrewAI 0.175.0+ requires `openai >= 1.13.3`. Ensure your environment satisfies this constraint.

#### Step 3: Configure Environment Variables

Create a `.env` file with your API keys:

```bash
FIRECRAWL_API_KEY=<your_firecrawl_api_key>
GROQ_API_KEY=<your_groq_api_key>
```

See the [LLM Configuration](#llm-configuration) section below for more details on setting up Groq.

## LLM Configuration

This tool uses a combination of locally hosted LLMs (via Ollama) and cloud-based LLMs (via Groq) for different tasks.

### Ollama Setup

1. Install Ollama from [ollama.ai](https://ollama.ai)

2. Pull the required models:
```bash
ollama pull llama3.1
ollama pull llama3.2
```

3. Start the Ollama service:
```bash
ollama serve
```

The service will run on `http://localhost:11434` by default.

### Groq Setup

1. Sign up for a Groq account at [groq.com](https://groq.com)

2. Get your API key from the Groq dashboard

3. Add your Groq API key to the `.env` file:
```bash
GROQ_API_KEY=<your_groq_api_key>
```

### Available Models

The tool uses different models for different tasks:

#### Groq Models
- **Llama 3 70B**: High-performance model for complex tasks
- **Llama 3 8B**: Efficient model for general tasks
- **Gemma 2 9B**: Google's model for focused analysis
- **Mixtral 8x7B**: Mixture of experts model for diverse tasks

#### Ollama Models
- **Llama 3.1**: Local model for research analysis
- **Llama 3.2**: Local model for writing tasks

### Model Configuration

Models can be configured in `config.py`. Default settings:
```python
# Groq Models
LLM_LLAMA70B = ChatGroq(model_name="llama3-70b-8192")
LLM_LLAMA8B = ChatGroq(model_name="llama3-8b-8192")
LLM_GEMMA2 = ChatGroq(model_name="gemma2-9b-it")
LLM_MIXTRAL = ChatGroq(model_name="mixtral-8x7b-32768")

# Ollama Models
LLM_OLLAMA3_1 = ChatOllama(
    model='llama3.1',
    timeout=120.0,
    temperature=0.5,
    streaming=True,
    base_url="http://localhost:11434",
    retry_on_failure=True,
    num_retries=3
)
```

### Troubleshooting LLMs

If you encounter LLM-related issues:

1. **Ollama Issues**
   - Ensure Ollama is running (`ollama serve`)
   - Check model availability (`ollama list`)
   - Verify port 11434 is available
   - Monitor system resources

2. **Groq Issues**
   - Verify API key in `.env`
   - Check Groq service status
   - Monitor API usage limits
   - Ensure internet connectivity

3. **General LLM Issues**
   - Check model loading errors
   - Monitor memory usage
   - Verify input lengths
   - Check for timeout settings

## Usage

### Basic Command

```bash
python d4bl.py "your research question here"
```

### Output Options

You can choose between two output formats:

1. Summary view (default):

```bash
python d4bl.py "your research question here" --output summary
```

2. Full detailed view:

```bash
python d4bl.py "your research question here" --output full
```

### Written Summary Options

Generate written summaries of different lengths using the `--summary` flag:

1. Brief summary (250-500 words):
```bash
python d4bl.py "your research question here" --summary brief
```

2. Detailed analysis (1000-1500 words):
```bash
python d4bl.py "your research question here" --summary detailed
```

3. Comprehensive report (2000-3000 words):
```bash
python d4bl.py "your research question here" --summary comprehensive
```

### View Example Topics

To see example research topics:

```bash
python d4bl.py examples
```

## Example Research Topics

The tool comes with pre-configured example topics such as:
- Algorithmic bias in criminal justice
- Impacts of data-driven policing
- Racial disparities in healthcare data
- Big data's role in housing discrimination

## Output Format

The tool provides:

### Summary Output
- Key Points extracted from research
- Main Themes identified
- Data Quality Assessment
  - Completeness score
  - Relevance score
  - Reliability score
- Recommendations based on analysis

### Full Output
- All summary information
- Raw research data
- Detailed analysis results
- Complete metadata

### Written Summaries

Each summary type follows specific guidelines:

#### Brief Summary (250-500 words)
- Focus on key findings and main implications
- 3-4 main points
- Structured in three paragraphs:
  - Context
  - Findings
  - Implications

#### Detailed Analysis (1000-1500 words)
- Thorough analysis of findings
- Methodology overview
- Multiple perspectives
- Detailed recommendations
- Organized with subheadings

#### Comprehensive Report (2000-3000 words)
- In-depth analysis
- Extensive context and background
- Detailed methodology
- Multiple case studies
- Thorough implications discussion
- Comprehensive recommendations
- Executive summary
- Citations and references

## File Outputs

The tool automatically saves results in three formats:

1. Research Results:
```bash
search_results_[query][timestamp].json
```

2. Analysis Results:
```bash
d4bl_research_[query][timestamp].json
```

3. Written Summaries:
```bash
summary_[format_type]_[query][timestamp].json
```

## Example Commands

1. Research with brief summary:
```bash
python d4bl.py "How does algorithmic bias affect criminal justice outcomes for Black communities?" --summary brief
```

2. Comprehensive analysis of healthcare disparities:
```bash
python d4bl.py "How can data science be used to address racial disparities in healthcare?" --summary comprehensive --output full
```

3. Detailed summary of housing discrimination:
```bash
python d4bl.py "What role does big data play in perpetuating housing discrimination?" --summary detailed
```

## Understanding Results

The tool provides:

1. Research Phase:
   - Web-scraped content
   - Relevant sources
   - Key information

2. Analysis Phase:
   - Key points extraction
   - Theme identification
   - Data quality assessment
   - Actionable recommendations

3. Writing Phase:
   - Structured summaries
   - Academic rigor
   - Clear narrative
   - Data justice focus
   - Actionable insights

## Best Practices

1. Be specific in your queries
2. Use clear, focused research questions
3. Consider multiple aspects of the issue
4. Choose appropriate summary length for your needs
5. Review both summary and full outputs
6. Save important results for future reference

## Troubleshooting

### Python Version Issues

**Error: "Python version not supported" or "requires Python >=3.10 and <3.14"**

If you have Python 3.14 or higher installed, you need to use a compatible version.

**Recommended Solution: Use pyenv**

1. **Install pyenv** (if not already installed):
   ```bash
   # macOS
   brew install pyenv
   
   # Linux
   curl https://pyenv.run | bash
   ```

2. **Set up pyenv in your shell** (add to ~/.zshrc or ~/.bashrc):
   ```bash
   export PYENV_ROOT="$HOME/.pyenv"
   command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
   eval "$(pyenv init -)"
   ```

3. **Install and set Python 3.13.9:**
   ```bash
   pyenv install 3.13.9
   cd /path/to/d4bl_ai_agent
   pyenv local 3.13.9
   ```

4. **Verify:**
   ```bash
   python --version  # Should show Python 3.13.9
   ```

**Alternative Solution: Direct Installation**

1. **Check your current Python version:**
   ```bash
   python3 --version
   ```

2. **Install Python 3.13:**
   ```bash
   # macOS
   brew install python@3.13
   
   # Linux (Ubuntu/Debian)
   sudo apt install python3.13 python3.13-venv python3.13-pip
   ```

3. **Use the specific Python version:**
   ```bash
   # With uv
   uv pip install -r requirements.txt --python python3.13
   
   # Or create a virtual environment
   python3.13 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Run scripts with the correct Python version:**
   ```bash
   python3.13 d4bl.py "your query here"
   ```

### General Issues

If you encounter other issues:

1. Check your API key in `.env`
2. Ensure all dependencies are installed
3. Verify internet connection
4. Check for rate limiting if making many requests
5. Ensure query is properly formatted (use quotes for multi-word queries)
6. Verify you're using a compatible Python version (see above)

## Contributing

To contribute to this tool:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

This tool is provided under the MIT License. See LICENSE file for details.

## Future Work

### Planned Improvements

#### 1. Frontend Interface
- Develop a web-based UI using React/Next.js
- Add interactive research topic exploration
- Implement real-time progress tracking
- Visualize analysis results and data relationships
- Create a dashboard for managing multiple research projects

#### 2. Additional AI Agents
- **Editor Agent**: Review and refine written summaries
- **Fact Checker Agent**: Verify claims and cross-reference sources
- **Citation Agent**: Ensure proper academic citations
- **Bias Detection Agent**: Identify and flag potential biases in research
- **Data Visualization Agent**: Create charts and graphs from findings

#### 3. Enhanced LLM Integration
- Fine-tune LLMs specifically for D4BL research topics
- Create a specialized D4BL knowledge base
- Implement domain-specific prompts and templates
- Develop evaluation metrics for data justice analysis

#### 4. Retrieval Augmented Generation (RAG)
- Build a D4BL-specific vector database
- Integrate academic papers and research
- Include community testimonies and case studies
- Implement semantic search capabilities
- Add real-time fact verification

#### 5. Deployment and Scaling
- Containerize application using Docker
- Set up CI/CD pipeline
- Deploy to cloud platforms (AWS/GCP/Azure)
- Implement load balancing for multiple users
- Add monitoring and logging systems

#### 6. Data Management
- Create structured database for research results
- Implement version control for reports
- Add collaborative research capabilities
- Enable project sharing and commenting
- Build export functionality for various formats

#### 7. Research Enhancement
- Add support for multiple research methodologies
- Implement comparative analysis features
- Enable longitudinal study tracking
- Add geographic data analysis
- Include demographic data integration

#### 8. Community Features
- Add user authentication and profiles
- Enable research sharing within communities
- Create discussion forums for findings
- Implement peer review system
- Add collaborative editing features

#### 9. API Development
- Create RESTful API for external integration
  - `/research` endpoint for initiating research
  - `/analysis` endpoint for analyzing existing research
  - `/summary` endpoint for generating summaries
  - `/status` endpoint for checking job progress
- Enable programmatic access to research tools
  - Python SDK for easy integration
  - API client libraries for multiple languages
  - Swagger/OpenAPI documentation
- Add webhook support for automation
  - Notification system for completed research
  - Integration with external workflows
  - Event-driven architecture
- Implement rate limiting and usage tracking
  - User-based quotas
  - Usage analytics
  - Cost tracking for LLM usage
- Create SDK for developers
  - Easy-to-use client libraries
  - Code examples and tutorials
  - Integration templates

Example API Usage:
```python
from d4bl_client import D4BLClient

client = D4BLClient(api_key="your_api_key")

# Start research
research_job = client.research.create(
    query="How does algorithmic bias affect criminal justice?",
    summary_type="detailed"
)

# Check status
status = client.research.get_status(research_job.id)

# Get results
if status.is_complete:
    results = client.research.get_results(research_job.id)
    summary = results.summary
    analysis = results.analysis
```

Planned API Endpoints:
```
POST /api/v1/research
GET  /api/v1/research/{job_id}
GET  /api/v1/research/{job_id}/status
POST /api/v1/analysis
POST /api/v1/summary
GET  /api/v1/jobs/{job_id}/results
```

#### 10. Documentation and Training
- Create comprehensive API documentation
- Develop user guides and tutorials
- Add interactive examples
- Create training materials for new users
- Build contribution guidelines

### Contributing to Future Development

We welcome contributions in the following areas:

1. **Code Contributions**
   - Bug fixes
   - Feature implementations
   - Performance improvements
   - Test coverage

2. **Documentation**
   - Technical documentation
   - User guides
   - Use case examples
   - Installation guides

3. **Research**
   - D4BL methodology development
   - LLM prompt engineering
   - Data justice frameworks
   - Evaluation metrics

4. **Testing**
   - Unit tests
   - Integration tests
   - User acceptance testing
   - Performance testing

To contribute:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request with detailed description
4. Follow the contribution guidelines