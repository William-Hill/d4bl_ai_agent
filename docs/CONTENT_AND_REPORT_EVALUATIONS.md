# Content and Report Relevance Evaluations

This document explains the new evaluation capabilities for assessing the relevance of extracted content and generated reports.

## Overview

Two new evaluation functions have been added to provide more granular feedback on research quality:

1. **Content Relevance Evaluation**: Evaluates how relevant the extracted content from URLs is to the query
2. **Report Relevance Evaluation**: Evaluates how relevant the final generated report is to the query

## Content Relevance Evaluation

### Purpose

Evaluates the relevance of content extracted from crawled URLs to the original research query. This helps identify:
- Whether the crawled sources contain relevant information
- If irrelevant sources are being used
- Quality of content extraction

### How It Works

1. **Extraction**: Content is extracted from crawl results (from the researcher agent's tool output)
2. **Evaluation**: Each extracted content is evaluated using an LLM to determine relevance (1-5 scale)
3. **Scoring**: Individual scores per URL and an average score across all sources

### Evaluation Criteria

- **5 (Highly relevant)**: Directly addresses the query
- **4 (Mostly relevant)**: Addresses most aspects of the query
- **3 (Moderately relevant)**: Somewhat related but may miss key aspects
- **2 (Weakly relevant)**: Tangentially related
- **1 (Not relevant)**: Does not address the query

### Usage

The evaluation runs automatically after research jobs complete. It extracts content from:
- Crawl tool results in research findings
- URLs with extracted content > 50 characters

### Output

```json
{
  "scores": {
    "https://example.com/article": {
      "score": 4.5,
      "explanation": "Directly addresses algorithmic bias in criminal justice..."
    }
  },
  "average": 4.2,
  "status": "success",
  "urls_evaluated": 5,
  "urls_total": 5
}
```

## Report Relevance Evaluation

### Purpose

Evaluates how well the final generated report addresses the original research query. This helps identify:
- Whether the report stays on-topic
- Missing aspects that should have been covered
- Overall alignment with the query

### How It Works

1. **Report Extraction**: The final report is read from `output/report.md`
2. **Evaluation**: The report is evaluated using an LLM against the original query
3. **Scoring**: A relevance score (1-5) with detailed feedback

### Evaluation Criteria

- **5 (Highly relevant)**: Comprehensively addresses the query
- **4 (Mostly relevant)**: Addresses most aspects of the query
- **3 (Moderately relevant)**: Addresses some aspects but misses key points
- **2 (Weakly relevant)**: Tangentially related to the query
- **1 (Not relevant)**: Does not address the query

### Additional Feedback

The evaluation also provides:
- **Key Points Addressed**: List of query aspects that are covered
- **Missing Aspects**: List of query aspects that are not well covered

### Usage

The evaluation runs automatically if a report file exists at `output/report.md`.

### Output

```json
{
  "relevance_score": 4.3,
  "explanation": "The report comprehensively covers algorithmic bias...",
  "key_points_addressed": [
    "Algorithmic bias definition",
    "Impact on Black communities",
    "Criminal justice outcomes"
  ],
  "missing_aspects": [
    "Recent 2025 developments"
  ],
  "status": "success"
}
```

## Integration

Both evaluations are integrated into the comprehensive evaluation system:

### Automatic Execution

- Runs after research jobs complete
- Included in the overall evaluation score
- Logged to Langfuse for tracking

### Overall Score Calculation

The overall evaluation score now includes:
1. Research Quality (existing)
2. Source Relevance (existing)
3. Bias Detection (existing)
4. Hallucination Detection (existing)
5. Reference Grounding (existing)
6. **Content Relevance** (new)
7. **Report Relevance** (new)

Skipped evaluations are excluded from the average.

## Configuration

No additional configuration is required. The evaluations use the same LLM configuration as other evaluations (Ollama by default).

## Benefits

1. **Early Detection**: Identify irrelevant sources before they affect the final report
2. **Quality Assurance**: Ensure reports stay on-topic
3. **Actionable Feedback**: Get specific feedback on what's missing or off-topic
4. **Continuous Improvement**: Track relevance scores over time

## Example Use Cases

### Use Case 1: Detecting Off-Topic Sources

If content relevance scores are low, it indicates:
- Search queries may need refinement
- Source filtering may be needed
- Better source selection criteria required

### Use Case 2: Report Quality Control

If report relevance is low, it indicates:
- Agents may be going off-topic
- Query may need clarification
- Report generation process may need improvement

## Troubleshooting

### Content Relevance Not Running

- Check if crawl results contain extracted content
- Verify content length > 50 characters
- Check logs for extraction errors

### Report Relevance Not Running

- Verify `output/report.md` exists
- Check file permissions
- Ensure report is generated by the writer agent

### Low Scores

- Review the explanation field for specific feedback
- Check if query is clear and specific
- Verify source quality and relevance
- Consider improving agent prompts

## Future Enhancements

Potential improvements:
- Real-time relevance checks during crawling
- Automatic source filtering based on relevance
- Report regeneration suggestions based on missing aspects
- Relevance-based source ranking

