from __future__ import annotations

from typing import Any

from d4bl.services.langfuse._base import EvalStatus, run_llm_evaluation
from d4bl.services.langfuse.prompts import hallucination_prompt
from d4bl.services.langfuse.parsers import parse_label_score


MAPPING = {
    "FACTUAL": 5.0,
    "HALLUCINATED": 1.0,
}


def evaluate_hallucination(
    query: str,
    answer: str,
    context: str,
    trace_id: str | None = None,
    llm: Any = None,
    langfuse: Any = None,
) -> dict[str, Any]:
    if not query or not query.strip():
        return {
            "error": "Query cannot be empty",
            "status": EvalStatus.FAILED,
            "error_type": "validation",
        }
    if not answer or not answer.strip():
        return {
            "error": "Answer cannot be empty",
            "status": EvalStatus.FAILED,
            "error_type": "validation",
        }
    if not context or not context.strip():
        return {
            "error": "Context cannot be empty",
            "status": EvalStatus.FAILED,
            "error_type": "validation",
        }

    def _parse(text: str) -> tuple[float, str]:
        score, explanation = parse_label_score(text, MAPPING, default_score=3.0)
        return score, str(explanation)

    result = run_llm_evaluation(
        eval_name="hallucination",
        prompt=hallucination_prompt(query, answer, context),
        parse_fn=_parse,
        score_key="hallucination_score",
        trace_id=trace_id,
        llm=llm,
        langfuse=langfuse,
    )
    # Rename feedback → explanation to match original API
    if "feedback" in result:
        result["explanation"] = result.pop("feedback")
    return result
