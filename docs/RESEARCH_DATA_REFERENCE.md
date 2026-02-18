# Research Data as Reference for Evaluations

This guide explains how research data collected during agentic workflows is automatically saved and used as reference data for LLM evaluations.

## Overview

When your CrewAI agents run, they gather research data through:
- **Web searches** (via FirecrawlSearchTool)
- **Agent outputs** (researcher, data_analyst, etc.)
- **Analysis results**

This research data is automatically extracted and saved to the database, then used as **reference data** (ground truth) for quality evaluations like:
- **HallucinationEvaluator**: Detects if outputs contain information not in the research data
- **RelevanceEvaluator**: Evaluates how relevant outputs are to the research findings

## How It Works

### 1. Automatic Research Data Extraction

When a research job completes, the system automatically:

1. **Extracts research data** from agent outputs:
   - Research findings from the `researcher` agent (contains Firecrawl web search results)
   - Analysis data from the `data_analyst` agent
   - Combined into a single reference document

2. **Saves to database**: Research data is stored in the `research_data` JSON column in the `research_jobs` table

3. **Structured format**:
   ```json
   {
     "research_findings": [
       {
         "agent": "Research Analyst",
         "description": "Research task description",
         "content": "Web search results and research findings..."
       }
     ],
     "analysis_data": [
       {
         "agent": "Data Analyst",
         "description": "Analysis task description",
         "content": "Analysis results..."
       }
     ],
     "all_research_content": "Combined research content for reference"
   }
   ```

### 2. Using Research Data in Evaluations

The evaluation script (`scripts/run_phoenix_evals.py`) automatically:

1. **Retrieves traces** from Phoenix
2. **Matches traces to research data** by:
   - Trace ID (if it matches a job_id)
   - Query text (matches against saved queries)
3. **Adds reference column** to evaluation DataFrame
4. **Uses appropriate evaluators**:
   - If reference data is available: Uses `HallucinationEvaluator` and `RelevanceEvaluator`
   - If no reference data: Uses only `ToxicityEvaluator`

## Setup

### 1. Add Database Column

Run the migration script to add the `research_data` column:

```bash
python scripts/add_research_data_column.py
```

Or manually add it via SQL:

```sql
ALTER TABLE research_jobs ADD COLUMN research_data JSON;
```

### 2. Run Research Jobs

Research data is automatically saved when you run research jobs through your API/UI. The data is extracted from:
- Researcher agent outputs (web search results)
- Data analyst outputs (analysis results)
- Other agent outputs that contain research content

### 3. Run Evaluations with Reference Data

```bash
# Using Ollama
python scripts/run_phoenix_evals.py --use-ollama

# Using OpenAI
python scripts/run_phoenix_evals.py
```

The script will automatically:
- Retrieve research data from the database
- Match it to traces
- Use evaluators that require reference data (if available)

## What Gets Saved as Research Data

### From Researcher Agent

The researcher agent uses FirecrawlSearchTool to search the web. The search results and findings are captured as research data:

- Web search query
- Search results content
- Synthesized research findings
- Source URLs and metadata

### From Data Analyst Agent

Analysis outputs that process research data:

- Data insights
- Pattern analysis
- Statistical findings
- Interpretations

### Combined Reference

All research content is combined into `all_research_content` which serves as the complete reference document for evaluations.

## Evaluation Types Enabled

With research data as reference, you can use:

### 1. HallucinationEvaluator
**Purpose**: Detects if the output contains information not present in the research data.

**Example**: If your agent claims "X happened in 2025" but your research data shows it happened in 2024, this will be flagged as a potential hallucination.

### 2. RelevanceEvaluator
**Purpose**: Evaluates how relevant the output is to the research findings.

**Example**: If the output discusses topics not covered in the research, relevance score will be lower.

### 3. QAEvaluator
**Purpose**: For question-answering tasks, checks if answers are correct based on research data.

**Example**: If asked "What is X?" and the answer matches the research data, it gets a high score.

## Example Workflow

1. **Run Research Job**:
   ```bash
   # Via API or UI
   POST /api/research
   {
     "query": "Latest trends in AI ethics",
     "summary_format": "detailed"
   }
   ```

2. **Research Data is Saved**:
   - Researcher agent searches web for "AI ethics trends"
   - Findings are saved to `research_data` column
   - Contains: web search results, synthesized findings, sources

3. **Run Evaluations**:
   ```bash
   python scripts/run_phoenix_evals.py --use-ollama
   ```

4. **Evaluations Use Research Data**:
   - Script retrieves research data from database
   - Matches it to traces by query/trace_id
   - Runs HallucinationEvaluator and RelevanceEvaluator
   - Outputs scores indicating:
     - Whether outputs contain hallucinations
     - How relevant outputs are to research findings

## Benefits

1. **Automatic Reference Generation**: No manual ground truth needed - research data serves as reference
2. **Quality Assurance**: Detect hallucinations and relevance issues automatically
3. **Continuous Improvement**: Track evaluation scores over time to improve agent performance
4. **Data-Driven**: Use actual research findings as the source of truth

## Troubleshooting

### No Research Data Found

If evaluations show "No reference data found":

1. **Check if research jobs completed**: Research data is only saved for completed jobs
2. **Verify database column exists**: Run `scripts/add_research_data_column.py`
3. **Check agent outputs**: Ensure researcher/data_analyst agents are producing output
4. **Verify matching**: Check that trace queries match saved job queries

### Research Data Not Matching Traces

If research data isn't being matched to traces:

1. **Check query matching**: The script matches by query text - ensure queries are similar
2. **Check trace_id**: If trace_id is a job_id UUID, it will match directly
3. **Manual matching**: You can manually add reference data to the evaluation DataFrame

## Manual Reference Data

You can also manually add reference data to evaluations:

```python
import pandas as pd
from phoenix.evals import HallucinationEvaluator, run_evals

df = pd.DataFrame({
    "input": ["What is AI?"],
    "output": ["AI is artificial intelligence..."],
    "reference": ["Your manual reference text here"]
})

results = run_evals(
    dataframe=df,
    evaluators=[HallucinationEvaluator()],
)
```

## Additional Resources

- [Phoenix Evaluators Guide](./PHOENIX_EVALUATORS.md)
- [Phoenix Evaluations Guide](./PHOENIX_EVALS.md)
- [Database Schema](./DATABASE.md)


