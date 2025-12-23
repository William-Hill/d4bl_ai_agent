# Error Handling and Langfuse Evaluations

This document describes the error handling improvements and Langfuse evaluation integration added to the D4BL AI Agent system.

## Overview

The system now includes:
1. **Robust error handling** with retry logic and fallback strategies
2. **Langfuse evaluations** for research quality assessment
3. **Comprehensive error recovery** mechanisms

## Error Handling Improvements

### 1. Crawl4AI Tool Retry Logic

The `Crawl4AISearchTool` now includes:

- **Exponential backoff retry**: Automatically retries failed requests with increasing delays (2s, 4s, 6s)
- **Smart error detection**: Distinguishes between retryable errors (503, 429, connection errors, timeouts) and non-retryable errors
- **Firecrawl fallback**: Automatically falls back to Firecrawl when Crawl4AI fails completely
- **Detailed error messages**: Provides actionable error information to help diagnose issues

**Location**: `src/d4bl/crew.py` - `Crawl4AISearchTool._crawl_urls_with_retry()`

### 2. Error Handling Utilities

A new `error_handling.py` module provides:

- **`retry_with_backoff` decorator**: Generic retry decorator with configurable backoff strategies
- **`safe_execute` function**: Safely execute functions with default return values
- **`ErrorRecoveryStrategy` class**: Predefined recovery strategies for common failure scenarios

**Location**: `src/d4bl/error_handling.py`

### 3. Crew Execution Error Handling

The crew execution now includes:

- **Input validation**: Validates required inputs before execution
- **Error recovery**: Attempts to return partial results when full execution fails
- **Comprehensive logging**: Logs all errors with full stack traces for debugging

**Location**: `src/d4bl/research_runner.py` - `run_research_job()`

## Langfuse Evaluations

### Evaluation Functions

Three evaluation functions are available:

1. **`evaluate_research_quality`**: Evaluates research output on:
   - Relevance (how well it addresses the query)
   - Completeness (comprehensiveness of information)
   - Accuracy (claims supported by sources)
   - Bias (balanced and free from harmful bias)
   - Clarity (well-structured and clear)

2. **`evaluate_source_relevance`**: Evaluates how relevant the sources are to the query

3. **`evaluate_bias_detection`**: Detects potential bias in research output

4. **`run_comprehensive_evaluation`**: Runs all evaluations and returns comprehensive results

**Location**: `src/d4bl/langfuse_evals.py`

### Integration

Evaluations are automatically run after each research job completes:

1. **Automatic execution**: After research completes, evaluations are triggered
2. **Source extraction**: Automatically extracts URLs from research findings
3. **Trace linking**: Links evaluations to the original Langfuse trace
4. **Result storage**: Stores evaluation results in the job result JSON

**Location**: `src/d4bl/research_runner.py` - `run_research_job()`

### Evaluation Results

Evaluation results are stored in:
- **Job result JSON**: `result["evaluation_results"]`
- **Langfuse scores**: Individual scores are logged to Langfuse for tracking over time

Example evaluation result structure:
```json
{
  "status": "success",
  "scores": {
    "relevance": 4.5,
    "completeness": 4.0,
    "accuracy": 4.2,
    "bias": 4.8,
    "clarity": 4.3,
    "overall": 4.36
  },
  "trace_id": "...",
  "evaluations": {
    "quality": {...},
    "source_relevance": {...},
    "bias": {...}
  }
}
```

## Configuration

### Environment Variables

No additional environment variables are required. The system uses existing Langfuse configuration:
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_HOST`

### Error Handling Configuration

Error handling is automatic and requires no configuration. However, you can customize:

- **Retry attempts**: Modify `max_retries` in `Crawl4AISearchTool._crawl_urls_with_retry()`
- **Backoff timing**: Adjust wait times in retry logic
- **Fallback behavior**: Configure Firecrawl API key for automatic fallback

## Usage

### Running Research Jobs

Research jobs automatically include error handling and evaluations:

```python
# In research_runner.py
result = await run_research_job(job_id, query, summary_format)
# Evaluations are automatically run and stored in result["evaluation_results"]
```

### Accessing Evaluation Results

Evaluation results are available in the job result:

```python
job = await get_job(job_id)
evaluation_results = job.result.get("evaluation_results")
if evaluation_results:
    overall_score = evaluation_results.get("overall_score")
    quality_scores = evaluation_results.get("evaluations", {}).get("quality", {})
```

### Viewing in Langfuse

1. Navigate to your Langfuse dashboard
2. Find the trace for your research job (using `trace_id`)
3. View evaluation scores in the trace details
4. Track evaluation trends over time using Langfuse analytics

## Error Recovery Strategies

The system implements several recovery strategies:

1. **Retry with backoff**: Automatically retries transient failures
2. **Service fallback**: Falls back to Firecrawl when Crawl4AI fails
3. **Partial results**: Returns partial results when full execution fails
4. **Graceful degradation**: Continues execution even when some components fail

## Monitoring and Debugging

### Logs

All errors are logged with:
- Full stack traces
- Context information (query, URLs, attempt numbers)
- Recovery actions taken

### Langfuse Traces

All operations are traced in Langfuse:
- Tool calls (Crawl4AI, Serper.dev)
- LLM invocations
- Evaluation runs
- Error occurrences

### Evaluation Metrics

Track evaluation metrics over time:
- Average quality scores
- Bias detection rates
- Source relevance trends
- Overall research quality

## Future Improvements

Potential enhancements:

1. **Caching**: Cache evaluation results for similar queries
2. **Custom evaluators**: Add domain-specific evaluators
3. **A/B testing**: Compare different research strategies
4. **Automated alerts**: Alert on low-quality research outputs
5. **Evaluation dashboards**: Create dashboards for evaluation metrics

## Troubleshooting

### Evaluations Not Running

1. Check Langfuse credentials are configured
2. Verify trace_id is available (check logs)
3. Check evaluation logs for errors

### High Error Rates

1. Check Crawl4AI service status
2. Verify network connectivity
3. Review retry logs for patterns
4. Consider adjusting retry parameters

### Low Evaluation Scores

1. Review evaluation feedback in results
2. Check source relevance scores
3. Verify research output quality
4. Adjust research prompts if needed

