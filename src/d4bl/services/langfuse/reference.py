from __future__ import annotations

from typing import Any, Dict, Optional

from d4bl.services.langfuse._base import EvalStatus, run_llm_evaluation
from d4bl.services.langfuse.prompts import reference_prompt
from d4bl.services.langfuse.parsers import parse_label_score


MAPPING = {
    "WELL_REFERENCED": 5.0,
    "WEAKLY_REFERENCED": 3.0,
    "UNGROUNDED": 1.0,
}


def evaluate_reference(
    query: str,
    answer: str,
    context: str,
    trace_id: Optional[str] = None,
    llm: Any = None,
    langfuse: Any = None,
) -> Dict[str, Any]:
    if not query or not query.strip():
        return {"error": "Query cannot be empty", "status": EvalStatus.FAILED, "error_type": "validation"}
    if not answer or not answer.strip():
        return {"error": "Answer cannot be empty", "status": EvalStatus.FAILED, "error_type": "validation"}
    if not context or not context.strip():
        return {"error": "Context cannot be empty", "status": EvalStatus.FAILED, "error_type": "validation"}

    def _parse(text: str) -> tuple[float, str]:
        score, explanation = parse_label_score(text, MAPPING, default_score=3.0)
        return score, str(explanation)

    result = run_llm_evaluation(
        eval_name="reference_grounding",
        prompt=reference_prompt(query, answer, context),
        parse_fn=_parse,
        score_key="reference_score",
        trace_id=trace_id,
        llm=llm,
        langfuse=langfuse,
    )
    if "feedback" in result:
        result["explanation"] = result.pop("feedback")
    return result
