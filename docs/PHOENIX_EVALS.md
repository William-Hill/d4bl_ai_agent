# Phoenix LLM Evaluations Guide

This guide explains how to run LLM evaluations on your CrewAI agents using Phoenix by Arize AI.

## Overview

Phoenix provides built-in evaluation capabilities that allow you to:
- **Evaluate traces**: Run evaluations on existing traces collected from your agents
- **Custom metrics**: Define custom evaluation metrics for your specific use cases
- **Built-in metrics**: Use pre-built metrics like relevance, correctness, and hallucination detection
- **Batch evaluation**: Evaluate multiple traces at once
- **Evaluation UI**: View evaluation results in the Phoenix UI

## Prerequisites

1. Phoenix is running and collecting traces (see [PHOENIX_SETUP.md](./PHOENIX_SETUP.md))
2. You have traces in Phoenix from running your CrewAI agents
3. Python environment with Phoenix installed
4. **LLM Provider**: Either:
   - **Ollama** (recommended, same as your agents): Set `USE_OLLAMA_FOR_EVALS=true` and ensure Ollama is running
   - **OpenAI**: Set `OPENAI_API_KEY` in your environment

## Installation

Phoenix Evals 2.0 uses separate packages. The required dependencies are in `requirements.txt`:

```bash
pip install -r requirements.txt
```

This includes:
- `arize-phoenix>=3.0.0` - Phoenix observability
- `arize-phoenix-evals>=2.0.0` - Phoenix Evals 2.0 (separate package for evaluations)
- `arize-phoenix-client>=1.19.0` - Phoenix client for API access
- `pandas>=2.0.0` - Required for running evaluations
- `litellm>=1.0.0` - Required for Ollama support in evaluators

**Note**: Phoenix Evals 2.0 is the recommended approach for evaluations. See the [official tutorial](https://github.com/Arize-ai/phoenix/blob/main/tutorials/evals/evals-2/evals_2.0_rag_demo.ipynb) for more details.

## Running Evaluations

### Method 1: Using the Evaluation Script (Recommended)

The project includes a comprehensive evaluation script (`scripts/run_evals_test.py`) that:
- Connects to Phoenix and retrieves traces
- Supports interactive job selection
- Runs evaluations using Ollama (same LLM as your agents)
- Saves results to the database for frontend display
- Logs annotations back to Phoenix

#### Basic Usage

```bash
# Run from inside Docker container
docker compose exec d4bl-api python /app/scripts/run_evals_test.py

# Interactive mode - select which job(s) to evaluate
docker compose exec d4bl-api python /app/scripts/run_evals_test.py --interactive

# Limit rows for faster testing
docker compose exec d4bl-api python /app/scripts/run_evals_test.py --max-rows 10 --eval-types bias

# Run specific evaluators
docker compose exec d4bl-api python /app/scripts/run_evals_test.py --eval-types bias hallucination
```

#### Command Line Options

- `--max-rows N`: Limit number of rows to evaluate (for faster debugging)
- `--eval-types TYPE1 TYPE2`: Which evaluators to run (`bias`, `hallucination`, `reference`)
- `--concurrency N`: Number of concurrent evaluation requests (default: 1)
- `--interactive`: Interactive mode to select which job(s) to evaluate

#### Interactive Mode

When using `--interactive`, the script will:
1. List all available jobs from the database
2. Show job ID, query preview, status, and Phoenix trace ID
3. Prompt you to select jobs by number (e.g., `1,3,5` or `all`)
4. Filter traces to only those matching selected jobs
5. Run evaluations and link results to the selected jobs

### Method 2: Using Phoenix UI

1. **Access Phoenix UI**: http://localhost:6006
2. **Navigate to Projects**: Click on "Projects" in the sidebar
3. **Select Your Project**: Click on your project (e.g., "d4bl-crewai")
4. **View Traces**: Traces are listed with their evaluation annotations
5. **View Evaluation Results**: Click on a trace to see evaluation scores and explanations

**Note**: Evaluation annotations are automatically logged back to Phoenix by the evaluation script, so they appear in the UI after running evaluations.

### Method 3: Using Python API Directly

Create a Python script to run evaluations programmatically:

```python
import phoenix as px
from phoenix.evals import (
    HallucinationEvaluator,
    RelevanceEvaluator,
    QAEvaluator,
    run_evals,
)

# Connect to your Phoenix instance
session = px.Client()

# Get traces from Phoenix
traces = session.get_traces()

# Define evaluators
hallucination_evaluator = HallucinationEvaluator()
relevance_evaluator = RelevanceEvaluator()

# Run evaluations
results = run_evals(
    dataframe=traces,
    evaluators=[hallucination_evaluator, relevance_evaluator],
    provide_explanation=True,
)

# View results
print(results)
```

### Method 3: Evaluating Specific Traces

You can evaluate specific traces by trace ID:

```python
import phoenix as px
from phoenix.evals import HallucinationEvaluator, run_evals

# Connect to Phoenix
session = px.Client()

# Get a specific trace
trace_id = "your-trace-id"
trace = session.get_trace(trace_id)

# Run evaluation
evaluator = HallucinationEvaluator()
result = evaluator.evaluate(
    input=trace.input,
    output=trace.output,
    reference=trace.reference,  # If available
)

print(f"Score: {result.score}")
print(f"Explanation: {result.explanation}")
```

## Built-in Evaluators

Phoenix provides several built-in evaluators:

### 1. HallucinationEvaluator
Detects hallucinations in LLM outputs by comparing against reference data.

```python
from phoenix.evals import HallucinationEvaluator

evaluator = HallucinationEvaluator()
```

### 2. RelevanceEvaluator
Evaluates how relevant the output is to the input query.

```python
from phoenix.evals import RelevanceEvaluator

evaluator = RelevanceEvaluator()
```

### 3. QAEvaluator
Evaluates question-answering tasks for correctness.

```python
from phoenix.evals import QAEvaluator

evaluator = QAEvaluator()
```

### 4. ToxicityEvaluator
Detects toxic or harmful content in outputs.

```python
from phoenix.evals import ToxicityEvaluator

evaluator = ToxicityEvaluator()
```

### 5. SummarizationEvaluator
Evaluates summarization quality.

```python
from phoenix.evals import SummarizationEvaluator

evaluator = SummarizationEvaluator()
```

## Custom Evaluators

You can create custom evaluators for your specific use cases:

```python
from phoenix.evals import LLMEvaluator
from phoenix.evals.models import OpenAIModel

class CustomEvaluator(LLMEvaluator):
    def __init__(self):
        super().__init__(
            model=OpenAIModel(model_name="gpt-4"),
            name="custom_evaluator",
        )
    
    def _create_prompt(self, input: str, output: str, reference: str = None) -> str:
        return f"""
        Evaluate the following output for your custom criteria:
        
        Input: {input}
        Output: {output}
        Reference: {reference if reference else "N/A"}
        
        Provide a score from 0-1 and an explanation.
        """
```

## Example: Evaluating CrewAI Agent Traces

Here's a complete example for evaluating your CrewAI agent traces:

```python
import phoenix as px
from phoenix.evals import HallucinationEvaluator, RelevanceEvaluator, run_evals
import pandas as pd

# Connect to Phoenix (running in Docker)
session = px.Client(api_key=None)  # No API key needed for local Phoenix

# Get traces from your project
traces = session.get_traces(project_name="d4bl-crewai")

# Prepare data for evaluation
# Extract input/output pairs from traces
eval_data = []
for trace in traces:
    # Extract the query (input)
    input_text = trace.attributes.get("input", "")
    
    # Extract the final output
    output_text = trace.attributes.get("output", "")
    
    eval_data.append({
        "input": input_text,
        "output": output_text,
        "trace_id": trace.id,
    })

df = pd.DataFrame(eval_data)

# Initialize evaluators
hallucination_evaluator = HallucinationEvaluator()
relevance_evaluator = RelevanceEvaluator()

# Run evaluations
results = run_evals(
    dataframe=df,
    evaluators=[hallucination_evaluator, relevance_evaluator],
    provide_explanation=True,
)

# Save results
results.to_csv("eval_results.csv")

# Print summary
print(f"Evaluated {len(results)} traces")
print(f"Average Hallucination Score: {results['hallucination_score'].mean()}")
print(f"Average Relevance Score: {results['relevance_score'].mean()}")
```

## Running Evaluations in a Script

Create a script to automate evaluations:

```python
# scripts/run_evals.py
import phoenix as px
from phoenix.evals import HallucinationEvaluator, RelevanceEvaluator, run_evals
import pandas as pd
import os

def evaluate_traces():
    # Connect to Phoenix
    # If running in Docker, Phoenix is accessible via service name
    phoenix_endpoint = os.getenv("PHOENIX_ENDPOINT", "http://localhost:6006")
    session = px.Client(endpoint=phoenix_endpoint)
    
    # Get traces
    traces = session.get_traces(project_name="d4bl-crewai")
    
    if not traces:
        print("No traces found. Run some agent tasks first.")
        return
    
    # Prepare evaluation data
    eval_data = []
    for trace in traces:
        # Extract relevant data from trace
        input_text = trace.attributes.get("input", "")
        output_text = trace.attributes.get("output", "")
        
        eval_data.append({
            "input": input_text,
            "output": output_text,
            "trace_id": trace.id,
        })
    
    df = pd.DataFrame(eval_data)
    
    # Run evaluations
    # Option 1: Use Ollama (recommended if you're using Ollama for your agents)
    from phoenix.evals.models import LiteLLMModel
    
    use_ollama = os.getenv("USE_OLLAMA_FOR_EVALS", "false").lower() == "true"
    if use_ollama:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ollama_model = os.getenv("OLLAMA_EVAL_MODEL", "mistral")
        os.environ["OLLAMA_API_BASE"] = ollama_base_url.rstrip('/')
        
        ollama_llm = LiteLLMModel(model_name=f"ollama/{ollama_model}", api_key="ollama")
        evaluators = [
            HallucinationEvaluator(model=ollama_llm),
            RelevanceEvaluator(model=ollama_llm),
        ]
    else:
        # Option 2: Use OpenAI (requires OPENAI_API_KEY)
        evaluators = [
            HallucinationEvaluator(),
            RelevanceEvaluator(),
        ]
    
    print(f"Evaluating {len(df)} traces...")
    results = run_evals(
        dataframe=df,
        evaluators=evaluators,
        provide_explanation=True,
    )
    
    # Save results
    output_file = "eval_results.csv"
    results.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")
    
    # Print summary
    print("\n=== Evaluation Summary ===")
    print(f"Total traces evaluated: {len(results)}")
    if 'hallucination_score' in results.columns:
        print(f"Average Hallucination Score: {results['hallucination_score'].mean():.2f}")
    if 'relevance_score' in results.columns:
        print(f"Average Relevance Score: {results['relevance_score'].mean():.2f}")

if __name__ == "__main__":
    evaluate_traces()
```

## Configuration

### Environment Variables

The evaluation script uses the following environment variables (set in `.env` or `docker-compose.yml`):

```bash
# Phoenix endpoint (automatically detected if running in Docker)
PHOENIX_ENDPOINT=http://phoenix:6006  # Inside Docker
# or
PHOENIX_ENDPOINT=http://localhost:6006  # On host

# Phoenix project name
PHOENIX_PROJECT_NAME=d4bl-crewai

# Ollama configuration (same as your agents)
OLLAMA_BASE_URL=http://host.docker.internal:11434  # Inside Docker
OLLAMA_MODEL_NAME=mistral
```

### Database Integration

The evaluation script automatically:
- Links evaluation results to jobs via `trace_id` (captured when jobs run)
- Saves evaluation results to the `evaluation_results` table
- Makes results available via the API endpoint `/api/evaluations`
- Displays results in the frontend when viewing a job

**Note**: If running in Docker, use `http://host.docker.internal:11434` for `OLLAMA_BASE_URL` to access Ollama on the host machine.

## Viewing Evaluation Results

### In Phoenix UI

1. **Access Phoenix UI**: http://localhost:6006
2. **Navigate to Your Project**: Go to Projects and select your project
3. **View Traces with Evaluations**: Traces that have been evaluated will show evaluation annotations
4. **Click on a Trace**: View detailed evaluation scores and explanations
5. **Filter and Analyze**: Use filters to find traces by score ranges, dates, or other criteria

### In the Frontend

Evaluation results are automatically displayed in the frontend:
1. Run a research job through the UI
2. After running evaluations, the results appear in the "LLM Evaluations" panel
3. Results are filtered by job, showing only evaluations for the selected job
4. View evaluation scores, labels, and explanations directly in the UI

### Via API

Query evaluation results via the API:

```bash
# Get all evaluations
curl http://localhost:8000/api/evaluations

# Get evaluations for a specific job
curl http://localhost:8000/api/evaluations?job_id=<job_id>

# Get evaluations for a specific trace
curl http://localhost:8000/api/evaluations?trace_id=<trace_id>
```

## Best Practices

1. **Start with Built-in Evaluators**: Use Phoenix's built-in evaluators first before creating custom ones
2. **Evaluate Regularly**: Run evaluations on a regular basis to track performance over time
3. **Use Multiple Metrics**: Combine multiple evaluators to get a comprehensive view
4. **Save Results**: Export evaluation results for analysis and reporting
5. **Monitor Trends**: Track evaluation scores over time to identify improvements or regressions

## Troubleshooting

### No Traces Found

If you get "No traces found":
1. Make sure Phoenix is running: `docker compose ps phoenix`
2. Run some agent tasks to generate traces
3. Check that traces are being sent to Phoenix (check API logs)

### Evaluation Errors

If evaluations fail:
1. **For Ollama**: 
   - Ensure Ollama is running: `ollama list`
   - Verify the model is available: `ollama pull mistral` (or your chosen model)
   - Check `OLLAMA_BASE_URL` is correct (use `http://host.docker.internal:11434` if running in Docker)
2. **For OpenAI**: 
   - Check that `OPENAI_API_KEY` is set correctly
3. Verify your Phoenix connection: `px.Client(endpoint="http://localhost:6006")`
4. Check that your traces have the required fields (input, output)

### Connection Issues

If you can't connect to Phoenix:
1. Verify Phoenix is running: `docker compose logs phoenix`
2. Check the endpoint URL (use `http://phoenix:6006` if running in Docker)
3. Ensure you're on the same network as Phoenix

## Additional Resources

- [Phoenix Evaluations Documentation](https://docs.arize.com/phoenix/evaluation)
- [Phoenix Evaluators Reference](https://docs.arize.com/phoenix/evaluation/evaluators)
- [Phoenix Python API](https://docs.arize.com/phoenix/api-reference/python-client)

## Persisting Evaluations in Postgres & Showing Them in the UI

Evaluations are now stored in two places automatically:

1. **Phoenix annotations** (unchanged) – still visible inside http://localhost:6006.
2. **Postgres (`evaluation_results` table)** – run the helper migration once:

```bash
python scripts/add_evaluation_results_table.py
```

Every time you execute `scripts/run_evals_test.py`, each evaluation row (hallucination, bias, reference) is inserted with span/trace IDs, label, score, explanation, and the underlying input/output/context. These rows are exposed through the FastAPI endpoint `GET /api/evaluations` and surfaced in the Next.js UI under the **“LLM Evaluations”** panel so you can review recent judgments without leaving the app.

The script still exports a CSV (`eval_results_with_explanations.csv`) for ad‑hoc analysis, giving you three synchronized views of the same data (Phoenix UI, Postgres/API, and CSV).

