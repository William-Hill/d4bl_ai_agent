from __future__ import annotations

def quality_prompt(query: str, research_output: str, sources: list[str]) -> str:
    newline = '\n'
    sources_list = newline.join(f'- {s}' for s in sources[:5])
    return f"""Evaluate the following research output for quality:

Original Query: {query}

Research Output:
{research_output[:2000]}...

Sources Used: {len(sources)} sources
{sources_list}

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


def content_relevance_prompt(query: str, url: str, content: str) -> str:
    return f"""Evaluate how relevant the extracted content from a URL is to the research query.

Original Query:
{query}

URL:
{url}

Extracted Content:
{content}

Evaluate the relevance of this content to the query on a scale of 1-5:
- 5: Highly relevant - directly addresses the query
- 4: Mostly relevant - addresses most aspects of the query
- 3: Moderately relevant - somewhat related but may miss key aspects
- 2: Weakly relevant - tangentially related
- 1: Not relevant - does not address the query

Consider:
- Does the content directly answer the query?
- Are key topics from the query covered?
- Is the information useful for addressing the query?

Respond with JSON: {{"relevance_score": <1-5>, "explanation": "brief explanation of the score"}}"""


def report_relevance_prompt(query: str, report: str) -> str:
    return f"""Evaluate how relevant the generated report is to the original research query.

Original Query:
{query}

Generated Report:
{report}

Evaluate the relevance of this report to the query on a scale of 1-5:
- 5: Highly relevant - comprehensively addresses the query
- 4: Mostly relevant - addresses most aspects of the query
- 3: Moderately relevant - addresses some aspects but misses key points
- 2: Weakly relevant - tangentially related to the query
- 1: Not relevant - does not address the query

Consider:
- Does the report directly answer the query?
- Are all key aspects of the query covered?
- Is the information organized and focused on the query?
- Are there missing aspects that should have been covered?

Respond with JSON: {{
    "relevance_score": <1-5>,
    "explanation": "brief explanation of the score",
    "key_points_addressed": ["list of key points from query that are addressed"],
    "missing_aspects": ["list of aspects from query that are missing or not well covered"]
}}"""
