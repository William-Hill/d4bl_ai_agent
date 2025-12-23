from __future__ import annotations

def quality_prompt(query: str, research_output: str, sources: list[str]) -> str:
    return f"""Evaluate the following research output for quality:

Original Query: {query}

Research Output:
{research_output[:2000]}...

Sources Used: {len(sources)} sources
{'\n'.join(f'- {s}' for s in sources[:5])}

Evaluate on the following criteria (1-5 scale):
1. Relevance: How well does the output address the query?
2. Completeness: How comprehensive is the information provided?
3. Accuracy: Are claims supported by sources?
4. Bias: Is the output balanced and free from harmful bias?
5. Clarity: Is the output well-structured and clear?

Provide scores and brief explanations for each criterion. Format as JSON with keys: relevance, completeness, accuracy, bias, clarity, overall, feedback."""


def bias_prompt(query: str, research_output: str) -> str:
    return f"""Analyze the following research output for potential bias:

Query: {query}

Output:
{research_output[:2000]}...

Identify:
1. Any racial, gender, or other demographic bias
2. Confirmation bias or one-sided perspectives
3. Missing perspectives or underrepresented viewpoints
4. Language that may perpetuate stereotypes

Provide a bias score (1-5, where 1=highly biased, 5=balanced) and explanation. Format as JSON with keys: bias_score, feedback."""
