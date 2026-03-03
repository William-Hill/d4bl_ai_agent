from __future__ import annotations

from typing import Any, Dict, Optional

from d4bl.services.langfuse._base import EvalStatus, run_llm_evaluation
from d4bl.services.langfuse.prompts import bias_prompt
from d4bl.services.langfuse.parsers import parse_bias_score


def evaluate_bias_detection(
    research_output: str,
    query: str,
    trace_id: Optional[str] = None,
    llm: Any = None,
    langfuse: Any = None,
) -> Dict[str, Any]:
    if not research_output or not research_output.strip():
        return {
            "error": "Research output cannot be empty",
            "status": EvalStatus.FAILED,
            "error_type": "validation",
        }
    if not query or not query.strip():
        return {
            "error": "Query cannot be empty",
            "status": EvalStatus.FAILED,
            "error_type": "validation",
        }

    return run_llm_evaluation(
        eval_name="bias_detection",
        prompt=bias_prompt(query, research_output),
        parse_fn=parse_bias_score,
        score_key="bias_score",
        trace_id=trace_id,
        llm=llm,
        langfuse=langfuse,
    )
