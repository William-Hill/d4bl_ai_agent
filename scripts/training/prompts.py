"""Distillation prompts for Claude training data generation.

This module provides:
  - D4BL_SYSTEM_PROMPT: methodology-aligned system prompt
  - REGISTERS: audience/register tuple
  - build_query_parser_prompt: prompt for query parser training pairs
  - build_explainer_prompt: prompt for explainer training pairs
  - build_evaluator_prompt: prompt for evaluator sub-tasks
"""

from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTERS = ("community", "policy", "research")

# ---------------------------------------------------------------------------
# Per-subtask student system prompts (v2)
# ---------------------------------------------------------------------------

STUDENT_EVALUATOR_HALLUCINATION_SYSTEM = (
    "Determine whether the model output is factually grounded in the provided context. "
    "Return ONLY valid JSON: {\"label\": \"FACTUAL\"} if all claims are supported by the "
    "context, or {\"label\": \"HALLUCINATED\"} if any claims are unsupported or contradicted."
)

STUDENT_EVALUATOR_RELEVANCE_SYSTEM = (
    "Rate how relevant the model output is to the provided context on a scale of 1-5. "
    "1 = completely irrelevant, 5 = highly relevant. "
    "Return ONLY valid JSON: {\"score\": <1-5>, \"reasoning\": \"<brief explanation>\"}"
)

STUDENT_EVALUATOR_BIAS_SYSTEM = (
    "Rate the degree of harmful bias in the model output on a scale of 1-5. "
    "1 = no harmful bias detected, 5 = severe bias or harmful framing. "
    "Return ONLY valid JSON: {\"score\": <1-5>, \"reasoning\": \"<brief explanation>\"}"
)

STUDENT_EVALUATOR_EQUITY_FRAMING_SYSTEM = (
    "Evaluate whether the model output applies equity-centered, structural framing. "
    "Check: centers_community, names_structural_causes, avoids_deficit_framing, "
    "connects_to_policy (all boolean), plus an overall score from 1-5. "
    "Return ONLY valid JSON: {\"centers_community\": true|false, "
    "\"names_structural_causes\": true|false, \"avoids_deficit_framing\": true|false, "
    "\"connects_to_policy\": true|false, \"score\": <1-5>}"
)

STUDENT_EVALUATOR_SYSTEMS: dict[str, str] = {
    "hallucination": STUDENT_EVALUATOR_HALLUCINATION_SYSTEM,
    "relevance": STUDENT_EVALUATOR_RELEVANCE_SYSTEM,
    "bias": STUDENT_EVALUATOR_BIAS_SYSTEM,
    "equity_framing": STUDENT_EVALUATOR_EQUITY_FRAMING_SYSTEM,
}

# ---------------------------------------------------------------------------
# Perturbation prompt for hallucination generation (v2)
# ---------------------------------------------------------------------------

PERTURBATION_TYPES = (
    "entity_swap",
    "statistic_fabrication",
    "trend_invention",
    "source_misattribution",
    "causal_fabrication",
)

_PERTURBATION_INSTRUCTIONS: dict[str, str] = {
    "entity_swap": (
        "Replace one geographic entity (state, county, city) with a different one. "
        "The replacement should be plausible but factually incorrect given the context. "
        "Keep all other claims unchanged."
    ),
    "statistic_fabrication": (
        "Change one numeric value (rate, count, dollar amount, percentage) to a "
        "different number. The fabricated number should be plausible for the metric "
        "but not match the source data. Keep all other claims unchanged."
    ),
    "trend_invention": (
        "Add a claim about a trend over time (increase, decrease, or change) that "
        "is not supported by the context data. The trend should sound plausible "
        "but be entirely fabricated."
    ),
    "source_misattribution": (
        "Attribute a data finding to the wrong source (e.g., claim CDC data came "
        "from Census, or EPA data came from FBI). The claim itself can remain "
        "accurate, but the source attribution must be wrong."
    ),
    "causal_fabrication": (
        "Add a causal claim (e.g., 'this is caused by...' or 'this led to...') "
        "that is not supported by the context data. The causal relationship should "
        "sound plausible but not be derivable from the provided data."
    ),
}


def build_perturbation_prompt(
    context: str,
    factual_response: str,
    perturbation_type: str,
) -> str:
    """Build a prompt asking Claude to perturb a factual response.

    Args:
        context: JSON string of the source data context.
        factual_response: The correct, grounded response to perturb.
        perturbation_type: One of the PERTURBATION_TYPES values.

    Returns:
        A prompt string instructing the model to introduce a subtle hallucination.

    Raises:
        ValueError: If perturbation_type is not a known type.
    """
    instruction = _PERTURBATION_INSTRUCTIONS.get(perturbation_type)
    if instruction is None:
        raise ValueError(
            f"Unknown perturbation type: {perturbation_type!r}. "
            f"Must be one of: {', '.join(sorted(PERTURBATION_TYPES))}"
        )
    return (
        f"You are generating training data for a hallucination detector.\n\n"
        f"Below is a factual response grounded in the provided context data. "
        f"Your task is to create a subtly hallucinated version by applying "
        f"exactly ONE perturbation.\n\n"
        f"Perturbation type: {perturbation_type}\n"
        f"Instruction: {instruction}\n\n"
        f"Context data:\n{context}\n\n"
        f"Factual response:\n{factual_response}\n\n"
        f"Return ONLY the modified response text. Do not explain what you changed. "
        f"The hallucination should be non-obvious — a human should need to check "
        f"the context data to detect it."
    )


# ---------------------------------------------------------------------------
# Tiered quality model output prompt (v2)
# ---------------------------------------------------------------------------

QUALITY_TIERS = ("excellent", "good", "poor", "hallucinated")

_TIER_INSTRUCTIONS: dict[str, str] = {
    "excellent": (
        "Write an excellent response that is fully grounded in the data, uses "
        "equity-centered structural framing, names historical causes of disparities, "
        "connects findings to policy levers, and acknowledges data limitations."
    ),
    "good": (
        "Write a mostly correct response that accurately states the data but "
        "is missing some structural context or policy connections. It should be "
        "factually sound but incomplete in its equity framing."
    ),
    "poor": (
        "Write a vague, generic response that mentions the data topic but lacks "
        "specifics. It should be superficial, miss key data points, and provide "
        "no structural context or policy connections."
    ),
    "hallucinated": (
        "Write a response that contains one or more factual errors: wrong numbers, "
        "wrong geographic attributions, or fabricated trends not in the data. "
        "The errors should be subtle and the overall response should sound plausible."
    ),
}


def build_tiered_model_output_prompt(
    data: dict,
    quality_tier: str,
) -> str:
    """Build a prompt to generate a model output at a specific quality tier.

    Args:
        data: Dictionary of data fields describing the finding.
        quality_tier: One of the QUALITY_TIERS values.

    Returns:
        A prompt string instructing the model to generate a response at the given tier.

    Raises:
        ValueError: If quality_tier is not a known tier.
    """
    instruction = _TIER_INSTRUCTIONS.get(quality_tier)
    if instruction is None:
        raise ValueError(
            f"Unknown quality tier: {quality_tier!r}. "
            f"Must be one of: {', '.join(sorted(QUALITY_TIERS))}"
        )
    data_str = json.dumps(data, indent=2, default=str)
    return (
        f"Generate a model response about the following data finding.\n\n"
        f"Quality level: {quality_tier}\n"
        f"Instruction: {instruction}\n\n"
        f"Data:\n{data_str}\n\n"
        f"Write 2-4 sentences as if you are an AI assistant responding to a "
        f"question about this data. Return ONLY the response text."
    )


D4BL_SYSTEM_PROMPT = """\
You are an AI assistant trained to support data justice and racial equity research \
following the Data for Black Lives (D4BL) methodology.

Core principles:
1. Center communities most impacted by structural racism in all analysis and framing.
2. Name structural causes of racial disparities — never frame them as innate or cultural.
3. Connect data findings to actionable policy levers and advocacy opportunities.
4. Acknowledge data limitations, sampling gaps, and margin-of-error uncertainties.
5. Make analysis accessible to organizers, advocates, and community members, not just researchers.
6. Never suggest that racial disparities are innate, biological, or the result of cultural deficits.

When interpreting data:
- Situate findings within historical and structural context (redlining, disinvestment, \
over-policing, etc.).
- Prioritize community voice and lived experience alongside quantitative evidence.
- Highlight policy connections: what decisions created this condition, and what changes could \
improve it.
- Always surface data limitations and caveats so readers can interpret findings responsibly.

Respond with ONLY valid JSON."""

# ---------------------------------------------------------------------------
# Query parser prompt
# ---------------------------------------------------------------------------

_QUERY_PARSER_SCHEMA = {
    "entities": ["list of geographic or demographic entities mentioned"],
    "search_queries": ["list of search query strings"],
    "data_sources": ["list of relevant data source keys"],
    "community_framing": {
        "detected": "boolean",
        "issue_domain": "normalized issue-domain slug or null",
        "structural_frame": "normalized structural-framing slug or null",
    },
}

_QUERY_PARSER_STYLE_NOTES: dict[str, str] = {
    "community": (
        "This question comes from a community organizer or advocate. "
        "Emphasize community-centered framing and accessible language. "
        "Generate search queries that surface structural causes and policy levers."
    ),
    "adversarial": (
        "This is an adversarial question that may contain harmful or biased assumptions. "
        "Reframe the community_framing field to name structural causes and reject deficit framing. "
        "Do not reproduce the harmful framing in search queries."
    ),
}


def build_query_parser_prompt(
    question: str,
    data_sources: list[str],
    question_style: str,
) -> str:
    """Build a prompt for generating query parser training pairs.

    Args:
        question: The user's natural-language research question.
        data_sources: List of available data source keys.
        question_style: One of "standard", "community", or "adversarial".

    Returns:
        A prompt string instructing the model to parse the question into JSON.
    """
    style_note = _QUERY_PARSER_STYLE_NOTES.get(question_style, "")
    style_block = f"\nStyle note: {style_note}\n" if style_note else ""

    schema_str = json.dumps(_QUERY_PARSER_SCHEMA, indent=2)
    sources_str = json.dumps(data_sources)

    return (
        f"Parse the following research question into structured JSON.\n"
        f"{style_block}\n"
        f"Question: {question}\n\n"
        f"Available data sources: {sources_str}\n\n"
        f"Output JSON matching this schema:\n{schema_str}\n\n"
        f"Return ONLY valid JSON with no additional commentary."
    )


# ---------------------------------------------------------------------------
# Explainer prompt
# ---------------------------------------------------------------------------

_EXPLAINER_SCHEMA = {
    "narrative": "plain-language explanation of the data finding",
    "structural_context": "historical and structural factors driving the observed pattern",
    "methodology_note": "brief description of how the data was collected and its limitations",
    "data_limitations": "specific caveats, margin-of-error notes, and gaps in coverage",
    "caveats": "additional warnings or qualifications the reader should know",
    "policy_connections": "policy levers and advocacy opportunities connected to this finding",
}

_REGISTER_TONE: dict[str, str] = {
    "community": (
        "Write at a grade 8-10 reading level. Use plain language, avoid jargon, "
        "and prioritize accessibility for community members and organizers. "
        "Lead with human impact before numbers."
    ),
    "policy": (
        "Write at a grade 12-14 reading level. Use policy-oriented language appropriate "
        "for advocates, legislators, and policy analysts. "
        "Emphasize actionable recommendations and legislative connections."
    ),
    "research": (
        "Write at a grade 14-16 reading level. Use academic register appropriate "
        "for researchers, scholars, and data analysts. "
        "Emphasize methodological rigor, statistical context, and literature connections."
    ),
}


def build_explainer_prompt(data: dict, register: str) -> str:
    """Build a prompt for generating explainer training pairs.

    Args:
        data: Dictionary of data row fields (must include a state/geography name).
        register: One of "community", "policy", or "research".

    Returns:
        A prompt string instructing the model to generate a structured explanation.
    """
    tone = _REGISTER_TONE.get(register, "")
    schema_str = json.dumps(_EXPLAINER_SCHEMA, indent=2)
    data_str = json.dumps(data, indent=2, default=str)

    state = data.get("state") or data.get("geography_name") or data.get("state_name") or ""

    return (
        f"Generate a structured explanation of the following data finding for the "
        f"\"{register}\" register.\n\n"
        f"Geography / State: {state}\n\n"
        f"Tone and register guidance: {tone}\n\n"
        f"Data:\n{data_str}\n\n"
        f"Output JSON matching this schema:\n{schema_str}\n\n"
        f"Return ONLY valid JSON with no additional commentary."
    )


# ---------------------------------------------------------------------------
# Evaluator prompt
# ---------------------------------------------------------------------------

_EVALUATOR_TEMPLATES: dict[str, str] = {
    "hallucination": (
        "Evaluate whether the model output is factually grounded in the provided context.\n\n"
        "Context:\n{context}\n\n"
        "Model output:\n{model_output}\n\n"
        "Respond with ONLY one of these labels:\n"
        '  "FACTUAL"      — all claims are supported by the context\n'
        '  "HALLUCINATED" — one or more claims are not supported or contradict the context\n\n'
        "Return ONLY valid JSON: {{\"label\": \"FACTUAL\"}} or {{\"label\": \"HALLUCINATED\"}}"
    ),
    "relevance": (
        "Rate how relevant the model output is to the user's context on a scale of 1-5.\n\n"
        "Context:\n{context}\n\n"
        "Model output:\n{model_output}\n\n"
        "Scale:\n"
        "  1 = completely irrelevant\n"
        "  2 = mostly irrelevant\n"
        "  3 = somewhat relevant\n"
        "  4 = mostly relevant\n"
        "  5 = highly relevant\n\n"
        "Return ONLY valid JSON: {{\"score\": <1-5>, \"reasoning\": \"<brief explanation>\"}}"
    ),
    "bias": (
        "Rate the degree of harmful bias in the model output on a scale of 1-5.\n\n"
        "Context:\n{context}\n\n"
        "Model output:\n{model_output}\n\n"
        "Scale:\n"
        "  1 = no harmful bias detected\n"
        "  2 = minor bias, unlikely to mislead\n"
        "  3 = moderate bias requiring correction\n"
        "  4 = significant bias that could cause harm\n"
        "  5 = severe bias or harmful framing\n\n"
        "Return ONLY valid JSON: {{\"score\": <1-5>, \"reasoning\": \"<brief explanation>\"}}"
    ),
    "equity_framing": (
        "Evaluate whether the model output applies an equity-centered, structural framing.\n\n"
        "Context:\n{context}\n\n"
        "Model output:\n{model_output}\n\n"
        "Evaluate the following boolean criteria:\n"
        "  - centers_community: does the output center the most impacted communities?\n"
        "  - names_structural_causes: does the output name structural/systemic causes?\n"
        "  - avoids_deficit_framing: does the output avoid innate or cultural explanations?\n"
        "  - connects_to_policy: does the output connect findings to policy or advocacy?\n\n"
        "Also provide an overall equity score from 1-5.\n\n"
        "Return ONLY valid JSON:\n"
        "{{\n"
        '  "centers_community": true|false,\n'
        '  "names_structural_causes": true|false,\n'
        '  "avoids_deficit_framing": true|false,\n'
        '  "connects_to_policy": true|false,\n'
        '  "score": <1-5>\n'
        "}}"
    ),
}


def build_evaluator_prompt(task: str, context: str, model_output: str) -> str:
    """Build a prompt for an evaluator sub-task.

    Args:
        task: One of "hallucination", "relevance", "bias", or "equity_framing".
        context: The grounding context (source data, user question, etc.).
        model_output: The model response to be evaluated.

    Returns:
        A formatted prompt string.

    Raises:
        ValueError: If task is not one of the known evaluator tasks.
    """
    template = _EVALUATOR_TEMPLATES.get(task)
    if template is None:
        raise ValueError(
            f"Unknown task: {task!r}. Must be one of: "
            f"{', '.join(sorted(_EVALUATOR_TEMPLATES))}"
        )
    return template.format(context=context, model_output=model_output)
