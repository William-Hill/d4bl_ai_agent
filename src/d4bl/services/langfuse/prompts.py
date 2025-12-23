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


def hallucination_prompt(query: str, answer: str, context: str) -> str:
    return f"""You are judging whether a model's answer is hallucinated or factual based on the provided context.

Query:
{query}

Context:
{context}

Answer:
{answer}

Classify the answer as exactly one label:
- FACTUAL: answer is supported by the context
- HALLUCINATED: answer is not supported or contradicts the context

Respond with JSON: {{"label": "FACTUAL" | "HALLUCINATED", "explanation": "..."}}"""


def reference_prompt(query: str, answer: str, context: str) -> str:
    return f"""You are judging how well the answer is grounded in the provided context.

Query:
{query}

Context:
{context}

Answer:
{answer}

Choose one label:
- WELL_REFERENCED   -> key claims clearly supported by context
- WEAKLY_REFERENCED -> loosely related but lacks strong support
- UNGROUNDED        -> not supported or contradicts context

Respond with JSON: {{"label": "WELL_REFERENCED" | "WEAKLY_REFERENCED" | "UNGROUNDED", "explanation": "..."}}"""
