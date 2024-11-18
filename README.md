# D4BL Research and Analysis Tool

This tool combines web research, data analysis, and writing capabilities to investigate topics related to Data for Black Lives (D4BL). It uses AI agents to gather information, analyze data, generate insights, and create written summaries about data justice and racial equity issues.

## Setup

1. Install the required dependencies: 

```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your Firecrawl API key:

```bash
FIRECRAWL_API_KEY=<your_firecrawl_api_key>
```

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

If you encounter issues:

1. Check your API key in `.env`
2. Ensure all dependencies are installed
3. Verify internet connection
4. Check for rate limiting if making many requests
5. Ensure query is properly formatted (use quotes for multi-word queries)

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