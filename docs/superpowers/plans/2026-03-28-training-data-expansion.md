# Training Data Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand evaluator training data from 160 to 1,400+ examples using perturbation-based hallucination generation, and query parser data from 434 to 734+ examples targeting new entity types — closing the gaps that caused 0% hallucination accuracy and 59% entity F1.

**Architecture:** Extend the existing `generate_training_pairs.py` distillation pipeline with new v2 generator functions. Evaluator expansion uses a three-step factual→perturb→format pipeline with per-subtask student prompts. Parser expansion adds entity-type-specific templates and 5 new seed tables. Both write to separate `_v2.jsonl` files; `prepare_dataset.py` merges via glob before dedup and split.

**Tech Stack:** Python, Anthropic Claude Sonnet 4 API, psycopg2, JSONL, pytest

**Spec:** `docs/superpowers/specs/2026-03-28-training-data-expansion-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/training/prompts.py` | Modify | Add per-subtask student prompts, perturbation prompt, tiered quality prompts, new parser templates |
| `scripts/training/config.py` | Modify | Add v2 constants |
| `scripts/training/generate_training_pairs.py` | Modify | Add v2 generator functions, new CLI tasks |
| `scripts/training/prepare_dataset.py` | Modify | Add glob-based merge, swap augmentation |
| `tests/test_training/test_prompts_v2.py` | Create | Tests for new prompts and templates |
| `tests/test_training/test_generate_pairs_v2.py` | Create | Tests for v2 generator pure functions |
| `tests/test_training/test_prepare_dataset_v2.py` | Create | Tests for merge and swap augmentation |

---

### Task 1: Add Per-Subtask Student Prompts to prompts.py

**Files:**
- Modify: `scripts/training/prompts.py`
- Create: `tests/test_training/test_prompts_v2.py`

- [ ] **Step 1: Write failing tests for per-subtask student prompts**

```python
# tests/test_training/test_prompts_v2.py
"""Tests for v2 prompt additions in scripts/training/prompts.py."""

from __future__ import annotations

from scripts.training.prompts import (
    STUDENT_EVALUATOR_HALLUCINATION_SYSTEM,
    STUDENT_EVALUATOR_RELEVANCE_SYSTEM,
    STUDENT_EVALUATOR_BIAS_SYSTEM,
    STUDENT_EVALUATOR_EQUITY_FRAMING_SYSTEM,
    STUDENT_EVALUATOR_SYSTEMS,
)


class TestPerSubtaskStudentPrompts:
    def test_hallucination_prompt_mentions_factual_label(self):
        assert "FACTUAL" in STUDENT_EVALUATOR_HALLUCINATION_SYSTEM
        assert "HALLUCINATED" in STUDENT_EVALUATOR_HALLUCINATION_SYSTEM

    def test_relevance_prompt_mentions_score_range(self):
        assert "1-5" in STUDENT_EVALUATOR_RELEVANCE_SYSTEM
        assert "score" in STUDENT_EVALUATOR_RELEVANCE_SYSTEM.lower()

    def test_bias_prompt_mentions_score_range(self):
        assert "1-5" in STUDENT_EVALUATOR_BIAS_SYSTEM
        assert "bias" in STUDENT_EVALUATOR_BIAS_SYSTEM.lower()

    def test_equity_framing_prompt_mentions_boolean_criteria(self):
        assert "centers_community" in STUDENT_EVALUATOR_EQUITY_FRAMING_SYSTEM
        assert "names_structural_causes" in STUDENT_EVALUATOR_EQUITY_FRAMING_SYSTEM

    def test_all_prompts_end_with_json_instruction(self):
        for prompt in STUDENT_EVALUATOR_SYSTEMS.values():
            assert "JSON" in prompt

    def test_systems_dict_has_all_four_subtasks(self):
        expected_keys = {"hallucination", "relevance", "bias", "equity_framing"}
        assert set(STUDENT_EVALUATOR_SYSTEMS.keys()) == expected_keys
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py -v`
Expected: FAIL with ImportError (constants not defined yet)

- [ ] **Step 3: Implement per-subtask student prompts**

Add to `scripts/training/prompts.py` after the existing `REGISTERS` constant (around line 19):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py -v`
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/training/prompts.py tests/test_training/test_prompts_v2.py
git commit -m "feat(training): add per-subtask evaluator student prompts (#139)"
```

---

### Task 2: Add Perturbation and Tiered Quality Prompts to prompts.py

**Files:**
- Modify: `scripts/training/prompts.py`
- Modify: `tests/test_training/test_prompts_v2.py`

- [ ] **Step 1: Write failing tests for perturbation and tiered quality prompts**

Append to `tests/test_training/test_prompts_v2.py`:

```python
from scripts.training.prompts import (
    build_perturbation_prompt,
    build_tiered_model_output_prompt,
    PERTURBATION_TYPES,
    QUALITY_TIERS,
)


class TestPerturbationPrompt:
    def test_build_includes_context(self):
        result = build_perturbation_prompt(
            context='{"state": "Mississippi", "metric": "poverty_rate", "value": 24.0}',
            factual_response="Mississippi has a poverty rate of 24%.",
            perturbation_type="statistic_fabrication",
        )
        assert "Mississippi" in result
        assert "poverty rate of 24%" in result

    def test_build_includes_perturbation_type(self):
        result = build_perturbation_prompt(
            context="{}",
            factual_response="Some response.",
            perturbation_type="entity_swap",
        )
        assert "entity" in result.lower() or "swap" in result.lower()

    def test_all_perturbation_types_defined(self):
        expected = {
            "entity_swap",
            "statistic_fabrication",
            "trend_invention",
            "source_misattribution",
            "causal_fabrication",
        }
        assert set(PERTURBATION_TYPES) == expected

    def test_raises_on_unknown_perturbation_type(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown perturbation type"):
            build_perturbation_prompt("{}", "resp", "made_up_type")


class TestTieredModelOutputPrompt:
    def test_build_includes_data(self):
        result = build_tiered_model_output_prompt(
            data={"state": "Alabama", "metric": "poverty_rate"},
            quality_tier="excellent",
        )
        assert "Alabama" in result

    def test_all_quality_tiers_defined(self):
        expected = {"excellent", "good", "poor", "hallucinated"}
        assert set(QUALITY_TIERS) == expected

    def test_raises_on_unknown_tier(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown quality tier"):
            build_tiered_model_output_prompt({}, "legendary")

    def test_excellent_tier_mentions_equity(self):
        result = build_tiered_model_output_prompt(
            data={"state": "Texas"},
            quality_tier="excellent",
        )
        assert "equity" in result.lower() or "structural" in result.lower()

    def test_poor_tier_mentions_vague(self):
        result = build_tiered_model_output_prompt(
            data={"state": "Texas"},
            quality_tier="poor",
        )
        assert "vague" in result.lower() or "generic" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py::TestPerturbationPrompt tests/test_training/test_prompts_v2.py::TestTieredModelOutputPrompt -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement perturbation and tiered quality prompts**

Add to `scripts/training/prompts.py` after the per-subtask student prompts:

```python
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
        context: The source data as a JSON string.
        factual_response: The verified factual narrative to perturb.
        perturbation_type: One of PERTURBATION_TYPES.

    Returns:
        A prompt string.

    Raises:
        ValueError: If perturbation_type is not recognized.
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
        data: Seed data row dict.
        quality_tier: One of QUALITY_TIERS.

    Returns:
        A prompt string.

    Raises:
        ValueError: If quality_tier is not recognized.
    """
    instruction = _TIER_INSTRUCTIONS.get(quality_tier)
    if instruction is None:
        raise ValueError(
            f"Unknown quality tier: {quality_tier!r}. "
            f"Must be one of: {', '.join(sorted(QUALITY_TIERS))}"
        )
    import json as _json
    data_str = _json.dumps(data, indent=2, default=str)
    return (
        f"Generate a model response about the following data finding.\n\n"
        f"Quality level: {quality_tier}\n"
        f"Instruction: {instruction}\n\n"
        f"Data:\n{data_str}\n\n"
        f"Write 2-4 sentences as if you are an AI assistant responding to a "
        f"question about this data. Return ONLY the response text."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py -v`
Expected: All 15 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/training/prompts.py tests/test_training/test_prompts_v2.py
git commit -m "feat(training): add perturbation and tiered quality prompts (#139)"
```

---

### Task 3: Add Parser Entity-Type Templates to prompts.py

**Files:**
- Modify: `scripts/training/prompts.py`
- Modify: `tests/test_training/test_prompts_v2.py`

- [ ] **Step 1: Write failing tests for entity-type templates**

Append to `tests/test_training/test_prompts_v2.py`:

```python
from scripts.training.prompts import (
    ENTITY_TYPE_TEMPLATES,
    ENTITY_TYPE_SEED_TABLES,
    ORG_NAMES,
    POLICY_NAMES,
)


class TestEntityTypeTemplates:
    def test_all_six_entity_types_defined(self):
        expected = {
            "organization",
            "policy",
            "sub_state_geography",
            "intersectional",
            "temporal",
            "adversarial_json",
        }
        assert set(ENTITY_TYPE_TEMPLATES.keys()) == expected

    def test_each_type_has_at_least_two_templates(self):
        for entity_type, templates in ENTITY_TYPE_TEMPLATES.items():
            assert len(templates) >= 2, f"{entity_type} has < 2 templates"

    def test_organization_templates_contain_org_placeholder(self):
        for template in ENTITY_TYPE_TEMPLATES["organization"]:
            assert "{org}" in template

    def test_policy_templates_contain_policy_placeholder(self):
        for template in ENTITY_TYPE_TEMPLATES["policy"]:
            assert "{policy}" in template

    def test_sub_state_templates_contain_county_or_city(self):
        for template in ENTITY_TYPE_TEMPLATES["sub_state_geography"]:
            assert "{county}" in template or "{city}" in template

    def test_temporal_templates_contain_event_or_policy(self):
        for template in ENTITY_TYPE_TEMPLATES["temporal"]:
            assert "{event}" in template or "{policy}" in template

    def test_org_names_is_non_empty_tuple(self):
        assert isinstance(ORG_NAMES, tuple)
        assert len(ORG_NAMES) >= 8

    def test_policy_names_is_non_empty_tuple(self):
        assert isinstance(POLICY_NAMES, tuple)
        assert len(POLICY_NAMES) >= 6


class TestEntityTypeSeedTables:
    def test_has_five_new_tables(self):
        expected = {
            "policy_bills",
            "bjs_incarceration",
            "vera_incarceration",
            "police_violence_incidents",
            "epa_environmental_justice",
        }
        assert expected.issubset(set(ENTITY_TYPE_SEED_TABLES))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py::TestEntityTypeTemplates tests/test_training/test_prompts_v2.py::TestEntityTypeSeedTables -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement entity-type templates**

Add to `scripts/training/prompts.py` after the tiered quality prompts:

```python
# ---------------------------------------------------------------------------
# Parser entity-type templates and seed data (v2)
# ---------------------------------------------------------------------------

ORG_NAMES = (
    "HUD", "CDC", "EPA", "NAACP", "Urban League", "Vera Institute",
    "Sentencing Project", "ACLU", "Brookings Institution", "Urban Institute",
    "National Fair Housing Alliance", "Equal Justice Initiative",
)

POLICY_NAMES = (
    "Affordable Care Act", "Section 8", "Title VI", "Fair Housing Act",
    "Voting Rights Act", "SNAP", "Medicaid expansion",
    "Community Reinvestment Act", "HOPE VI", "No Child Left Behind",
)

ENTITY_TYPE_TEMPLATES: dict[str, list[str]] = {
    "organization": [
        "What has {org} reported about {metric} in {state}?",
        "How does {org}'s data compare to {org2}'s findings on {metric}?",
        "According to {org}, what are the {metric} disparities in {state}?",
        "What recommendations has {org} made regarding {metric} for {race} communities?",
    ],
    "policy": [
        "How has {policy} affected {metric} for {race} communities in {state}?",
        "What data exists on {policy} outcomes in {state}?",
        "Has {policy} reduced {metric} disparities in {state}?",
        "Compare {metric} before and after {policy} implementation in {state}.",
    ],
    "sub_state_geography": [
        "Compare {metric} between {county} and {county2} in {state}.",
        "What are {metric} rates in {city}, {state}?",
        "How does {county} in {state} compare to the state average for {metric}?",
        "Which counties in {state} have the worst {metric} outcomes?",
    ],
    "intersectional": [
        "What are {metric} outcomes for low-income {race} families in {state}?",
        "How does {metric} affect elderly {race} homeowners versus renters in {state}?",
        "What do the data show about {metric} for {race} women in {state}?",
        "Compare {metric} for rural versus urban {race} communities in {state}.",
    ],
    "temporal": [
        "How has {metric} changed in {state} since {event}?",
        "What were {metric} trends before and after {policy} in {state}?",
        "Show me {metric} data for {state} from {year} to {year2}.",
    ],
    "adversarial_json": [
        "what's the deal with {metric} in {state}?? like is it bad or what",
        "{metric}",
        "Tell me EVERYTHING about {metric} and {metric2} and also {metric3} and poverty and crime and health and education in {state} and also {state2} and nationally and historically",
        "What is the {metric} rate in {state}? (please format as a table, not JSON)",
        'How about {metric} in "{state}" — any \'good\' news?',
    ],
}

ENTITY_TYPE_SEED_TABLES = (
    "policy_bills",
    "bjs_incarceration",
    "vera_incarceration",
    "police_violence_incidents",
    "epa_environmental_justice",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prompts_v2.py -v`
Expected: All 25 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/training/prompts.py tests/test_training/test_prompts_v2.py
git commit -m "feat(training): add entity-type templates for parser expansion (#139)"
```

---

### Task 4: Add v2 Config Constants

**Files:**
- Modify: `scripts/training/config.py`

- [ ] **Step 1: Add v2 constants to config.py**

Add after the existing `JACCARD_THRESHOLD` line (line 30) in `scripts/training/config.py`:

```python
# V2 expansion (issue #139)
EVALUATOR_V2_PAIRS_PER_SUBTASK = 350  # targets 300+ post-dedup
PARSER_V2_ENTITY_PAIRS = 300
```

- [ ] **Step 2: Verify import works**

Run: `source .venv/bin/activate && python -c "from scripts.training.config import EVALUATOR_V2_PAIRS_PER_SUBTASK, PARSER_V2_ENTITY_PAIRS; print(f'eval={EVALUATOR_V2_PAIRS_PER_SUBTASK}, parser={PARSER_V2_ENTITY_PAIRS}')"`
Expected: `eval=350, parser=300`

- [ ] **Step 3: Commit**

```bash
git add scripts/training/config.py
git commit -m "feat(training): add v2 expansion config constants (#139)"
```

---

### Task 5: Implement Evaluator v2 Generator (Pure Functions)

**Files:**
- Modify: `scripts/training/generate_training_pairs.py`
- Create: `tests/test_training/test_generate_pairs_v2.py`

- [ ] **Step 1: Write failing tests for evaluator v2 pure functions**

```python
# tests/test_training/test_generate_pairs_v2.py
"""Tests for v2 generator functions — pure functions only, no API calls."""

from __future__ import annotations

import json

from scripts.training.generate_training_pairs import (
    build_hallucination_pair,
    build_evaluator_v2_pair,
    generate_query_parser_questions_v2,
)
from scripts.training.prompts import STUDENT_EVALUATOR_SYSTEMS


class TestBuildHallucinationPair:
    """Test the function that formats factual+hallucinated into training pairs."""

    _SEED_ROW = {"state": "Mississippi", "metric": "poverty_rate", "value": 24.0}
    _FACTUAL = "Mississippi has a poverty rate of 24%."
    _HALLUCINATED = "Vermont has a poverty rate of 24%."

    def test_returns_two_pairs(self):
        result = build_hallucination_pair(
            seed_row=self._SEED_ROW,
            factual_response=self._FACTUAL,
            hallucinated_response=self._HALLUCINATED,
        )
        assert len(result) == 2

    def test_first_pair_is_factual(self):
        factual_pair, _ = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        assistant = json.loads(factual_pair["messages"][2]["content"])
        assert assistant["label"] == "FACTUAL"

    def test_second_pair_is_hallucinated(self):
        _, hallucinated_pair = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        assistant = json.loads(hallucinated_pair["messages"][2]["content"])
        assert assistant["label"] == "HALLUCINATED"

    def test_both_pairs_use_hallucination_system_prompt(self):
        factual_pair, hall_pair = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        expected_system = STUDENT_EVALUATOR_SYSTEMS["hallucination"]
        assert factual_pair["messages"][0]["content"] == expected_system
        assert hall_pair["messages"][0]["content"] == expected_system

    def test_factual_pair_user_contains_factual_response(self):
        factual_pair, _ = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        user_content = factual_pair["messages"][1]["content"]
        assert self._FACTUAL in user_content

    def test_hallucinated_pair_user_contains_hallucinated_response(self):
        _, hall_pair = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        user_content = hall_pair["messages"][1]["content"]
        assert self._HALLUCINATED in user_content


class TestBuildEvaluatorV2Pair:
    """Test formatting for relevance, bias, and equity_framing subtasks."""

    _SEED_ROW = {"state": "Alabama", "metric": "uninsured_rate", "value": 0.19}
    _MODEL_OUTPUT = "Alabama has an uninsured rate of 19%."
    _JUDGMENT = {"score": 4, "reasoning": "Relevant and accurate."}

    def test_returns_single_pair(self):
        result = build_evaluator_v2_pair(
            subtask="relevance",
            seed_row=self._SEED_ROW,
            model_output=self._MODEL_OUTPUT,
            judgment=self._JUDGMENT,
        )
        assert isinstance(result, dict)
        assert "messages" in result

    def test_uses_correct_subtask_system_prompt(self):
        result = build_evaluator_v2_pair(
            subtask="bias",
            seed_row=self._SEED_ROW,
            model_output=self._MODEL_OUTPUT,
            judgment=self._JUDGMENT,
        )
        assert result["messages"][0]["content"] == STUDENT_EVALUATOR_SYSTEMS["bias"]

    def test_user_message_contains_context_and_output(self):
        result = build_evaluator_v2_pair(
            subtask="relevance",
            seed_row=self._SEED_ROW,
            model_output=self._MODEL_OUTPUT,
            judgment=self._JUDGMENT,
        )
        user_content = result["messages"][1]["content"]
        assert "Alabama" in user_content
        assert "19%" in user_content

    def test_assistant_message_is_valid_json(self):
        result = build_evaluator_v2_pair(
            subtask="relevance",
            seed_row=self._SEED_ROW,
            model_output=self._MODEL_OUTPUT,
            judgment=self._JUDGMENT,
        )
        parsed = json.loads(result["messages"][2]["content"])
        assert parsed["score"] == 4


class TestGenerateQueryParserQuestionsV2:
    """Test entity-type-specific question generation."""

    _SEED_ROWS = [
        {"state": "Mississippi", "metric_name": "poverty_rate", "race": "Black", "year": 2022},
        {"state": "Alabama", "metric_name": "uninsured_rate", "race": "Hispanic", "year": 2021},
    ]

    def test_returns_requested_count(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=5, entity_type="organization",
        )
        assert len(result) == 5

    def test_each_item_has_question_and_style(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=3, entity_type="policy",
        )
        for item in result:
            assert "question" in item
            assert "entity_type" in item
            assert item["entity_type"] == "policy"

    def test_organization_questions_contain_org_name(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=5, entity_type="organization",
        )
        from scripts.training.prompts import ORG_NAMES
        for item in result:
            assert any(org in item["question"] for org in ORG_NAMES)

    def test_adversarial_json_returns_stress_questions(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=3, entity_type="adversarial_json",
        )
        assert len(result) == 3
        for item in result:
            assert item["entity_type"] == "adversarial_json"

    def test_count_zero_returns_empty(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=0, entity_type="organization",
        )
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_generate_pairs_v2.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement the pure helper functions**

Add to `scripts/training/generate_training_pairs.py` after the existing `format_as_chatml` function (around line 219):

```python
from scripts.training.prompts import (
    STUDENT_EVALUATOR_SYSTEMS,
    ENTITY_TYPE_TEMPLATES,
    ORG_NAMES,
    POLICY_NAMES,
)


def build_hallucination_pair(
    seed_row: dict,
    factual_response: str,
    hallucinated_response: str,
) -> tuple[dict, dict]:
    """Build a (FACTUAL, HALLUCINATED) pair for hallucination detection training.

    Returns:
        Tuple of (factual_pair, hallucinated_pair) in ChatML format.
    """
    system = STUDENT_EVALUATOR_SYSTEMS["hallucination"]
    context = json.dumps(seed_row, ensure_ascii=False, default=str)

    factual_pair = format_as_chatml(
        system=system,
        user=f"Context:\n{context}\n\nModel output:\n{factual_response}",
        assistant=json.dumps({"label": "FACTUAL"}),
    )
    hallucinated_pair = format_as_chatml(
        system=system,
        user=f"Context:\n{context}\n\nModel output:\n{hallucinated_response}",
        assistant=json.dumps({"label": "HALLUCINATED"}),
    )
    return factual_pair, hallucinated_pair


def build_evaluator_v2_pair(
    subtask: str,
    seed_row: dict,
    model_output: str,
    judgment: dict,
) -> dict:
    """Build a single evaluator training pair for relevance/bias/equity_framing.

    Args:
        subtask: One of "relevance", "bias", "equity_framing".
        seed_row: Source data row dict.
        model_output: The model response being evaluated.
        judgment: The expected evaluator judgment dict.

    Returns:
        ChatML-formatted training pair.
    """
    system = STUDENT_EVALUATOR_SYSTEMS[subtask]
    context = json.dumps(seed_row, ensure_ascii=False, default=str)
    return format_as_chatml(
        system=system,
        user=f"Context:\n{context}\n\nModel output:\n{model_output}",
        assistant=json.dumps(judgment, ensure_ascii=False),
    )


_TEMPORAL_EVENTS = (
    "the 2008 recession", "COVID-19", "the Affordable Care Act",
    "the 2020 census", "Hurricane Katrina", "the Great Migration",
)


def generate_query_parser_questions_v2(
    seed_rows: list[dict],
    count: int,
    entity_type: str,
) -> list[dict]:
    """Generate questions for a specific entity type using v2 templates.

    Args:
        seed_rows: Seed data rows for template variable extraction.
        count: Number of questions to generate.
        entity_type: Key into ENTITY_TYPE_TEMPLATES.

    Returns:
        List of dicts with "question", "entity_type", and "seed_data" keys.
    """
    if count == 0:
        return []

    templates = ENTITY_TYPE_TEMPLATES[entity_type]
    results: list[dict] = []

    for i in range(count):
        row = seed_rows[i % len(seed_rows)]
        template = templates[i % len(templates)]
        vars_ = _extract_template_vars(row)
        # Add entity-type-specific variables
        vars_["org"] = ORG_NAMES[i % len(ORG_NAMES)]
        vars_["org2"] = ORG_NAMES[(i + 1) % len(ORG_NAMES)]
        vars_["policy"] = POLICY_NAMES[i % len(POLICY_NAMES)]
        vars_["county"] = row.get("county_name", row.get("geography_name", "Cook County"))
        vars_["county2"] = "Harris County"
        vars_["city"] = row.get("city", "Chicago")
        vars_["event"] = _TEMPORAL_EVENTS[i % len(_TEMPORAL_EVENTS)]
        vars_["year2"] = str(int(vars_["year"]) + 3)
        vars_["metric2"] = "unemployment"
        vars_["metric3"] = "incarceration"
        vars_["state2"] = "California"
        vars_["demographic"] = "families"
        try:
            question = template.format(**vars_)
        except KeyError:
            question = template.format_map(vars_)
        results.append({
            "question": question,
            "entity_type": entity_type,
            "seed_data": row,
        })

    return results
```

Also update the imports at the top of `generate_training_pairs.py` — add to the existing `from scripts.training.prompts import` block:

```python
from scripts.training.prompts import (
    D4BL_SYSTEM_PROMPT,
    ENTITY_TYPE_TEMPLATES,
    ORG_NAMES,
    POLICY_NAMES,
    REGISTERS,
    STUDENT_EVALUATOR_SYSTEMS,
    build_evaluator_prompt,
    build_explainer_prompt,
    build_perturbation_prompt,
    build_query_parser_prompt,
    build_tiered_model_output_prompt,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_generate_pairs_v2.py -v`
Expected: All 15 tests PASSED

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_generate_pairs.py tests/test_training/test_prompts.py -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/training/generate_training_pairs.py tests/test_training/test_generate_pairs_v2.py
git commit -m "feat(training): add evaluator v2 and parser v2 pure helper functions (#139)"
```

---

### Task 6: Implement Evaluator v2 High-Level Generator

**Files:**
- Modify: `scripts/training/generate_training_pairs.py`

This task adds the `generate_evaluator_pairs_v2()` function that orchestrates the three-step factual→perturb→format pipeline and the tiered quality generation. This function calls the Claude API and cannot be unit-tested without mocking.

- [ ] **Step 1: Implement generate_evaluator_pairs_v2**

Add to `scripts/training/generate_training_pairs.py` after the existing `generate_evaluator_pairs` function:

```python
from scripts.training.config import EVALUATOR_V2_PAIRS_PER_SUBTASK
from scripts.training.prompts import (
    PERTURBATION_TYPES,
    QUALITY_TIERS,
    build_perturbation_prompt,
    build_tiered_model_output_prompt,
)


def _generate_factual_response(seed_row: dict) -> str | None:
    """Call Claude to generate a grounded narrative from a seed row.

    Returns the response text, or None if the call fails.
    """
    data_str = json.dumps(seed_row, ensure_ascii=False, default=str)
    prompt = (
        f"Write a 2-4 sentence factual summary of the following data. "
        f"Ground every claim in the provided data. Do not add information "
        f"not present in the data.\n\nData:\n{data_str}"
    )
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Factual response generation failed: {exc}", flush=True)
        return None


def _perturb_to_hallucination(
    seed_row: dict,
    factual_response: str,
    perturbation_type: str,
) -> str | None:
    """Call Claude to create a hallucinated version of a factual response.

    Returns the perturbed text, or None if the call fails.
    """
    context = json.dumps(seed_row, ensure_ascii=False, default=str)
    prompt = build_perturbation_prompt(context, factual_response, perturbation_type)
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Perturbation failed: {exc}", flush=True)
        return None


def _generate_tiered_model_output(seed_row: dict, quality_tier: str) -> str | None:
    """Call Claude to generate a model output at a specific quality tier.

    Returns the response text, or None if the call fails.
    """
    prompt = build_tiered_model_output_prompt(seed_row, quality_tier)
    try:
        return _call_claude(D4BL_SYSTEM_PROMPT, prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Tiered output generation failed ({quality_tier}): {exc}", flush=True)
        return None


def generate_evaluator_pairs_v2(
    conn: Any,
    count_per_subtask: int = EVALUATOR_V2_PAIRS_PER_SUBTASK,
    outfile: Path | None = None,
) -> list[dict]:
    """Generate v2 evaluator training pairs using perturbation-based hallucinations.

    Hallucination subtask uses a three-step factual->perturb->format pipeline.
    Relevance, bias, equity_framing use tiered quality model outputs.

    Args:
        conn: A live psycopg2 connection.
        count_per_subtask: Number of pairs per subtask before dedup.
        outfile: Optional output path for incremental writes.

    Returns:
        A shuffled list of ChatML pair dicts.
    """
    seed_rows = _load_seed_rows(conn, limit=400)
    all_pairs: list[dict] = []
    call_count = 0

    # --- Hallucination subtask: perturbation pipeline ---
    print("[evaluator_v2/hallucination] Starting perturbation pipeline...", flush=True)
    hall_count = count_per_subtask // 2  # Each generates 2 pairs (factual + hallucinated)
    perturbation_types = list(PERTURBATION_TYPES)

    for idx in range(hall_count):
        if call_count > 0 and call_count % 25 == 0:
            time.sleep(1)

        row = seed_rows[idx % len(seed_rows)]
        ptype = perturbation_types[idx % len(perturbation_types)]

        # Step 1: Generate factual response
        factual = _generate_factual_response(row)
        call_count += 1
        if not factual:
            continue

        # Step 2: Perturb to hallucination
        hallucinated = _perturb_to_hallucination(row, factual, ptype)
        call_count += 1
        if not hallucinated:
            continue

        # Step 3: Format as training pairs
        factual_pair, hall_pair = build_hallucination_pair(row, factual, hallucinated)
        all_pairs.extend([factual_pair, hall_pair])
        print(
            f"[evaluator_v2/hallucination] {len(all_pairs)} pairs "
            f"({idx + 1}/{hall_count} seeds)", flush=True,
        )

    # --- Relevance, bias, equity_framing: tiered quality outputs ---
    non_hall_subtasks = ["relevance", "bias", "equity_framing"]
    tiers = [t for t in QUALITY_TIERS if t != "hallucinated"]  # excellent, good, poor
    # Add "hallucinated" tier separately since it's handled differently in evaluator

    for subtask in non_hall_subtasks:
        print(f"[evaluator_v2/{subtask}] Starting tiered generation...", flush=True)
        for idx in range(count_per_subtask):
            if call_count > 0 and call_count % 25 == 0:
                time.sleep(1)

            row = seed_rows[idx % len(seed_rows)]
            tier = QUALITY_TIERS[idx % len(QUALITY_TIERS)]

            # Generate model output at this quality tier
            model_output = _generate_tiered_model_output(row, tier)
            call_count += 1
            if not model_output:
                continue

            # Get Claude's judgment for this subtask
            teacher_prompt = build_evaluator_prompt(
                task=subtask,
                context=json.dumps(row, ensure_ascii=False, default=str),
                model_output=model_output,
            )
            try:
                response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] Evaluator judgment failed for {subtask}: {exc}", flush=True)
                call_count += 1
                continue
            call_count += 1

            validated = _validate_json(response_text)
            if validated is None:
                print(f"[warn] Invalid JSON for {subtask} pair {idx}, skipping.", flush=True)
                continue

            pair = build_evaluator_v2_pair(subtask, row, model_output, validated)
            all_pairs.append(pair)
            print(
                f"[evaluator_v2/{subtask}] {len(all_pairs)} total pairs", flush=True,
            )

    random.shuffle(all_pairs)

    if outfile is not None:
        write_jsonl(all_pairs, outfile)
        print(f"[evaluator_v2] Saved {len(all_pairs)} pairs to {outfile}", flush=True)

    _print_cost_summary()
    return all_pairs
```

- [ ] **Step 2: Wire into the CLI**

In the `main()` function of `generate_training_pairs.py`, add `evaluator_v2` to the task map (around line 697):

```python
        _TASK_MAP = {
            "query_parser": lambda: generate_query_parser_pairs(
                conn, count=PAIRS_PER_TASK, outfile=PAIRS_DIR / "query_parser.jsonl",
            ),
            "explainer": lambda: generate_explainer_pairs(
                conn, count=PAIRS_PER_TASK, outfile=PAIRS_DIR / "explainer.jsonl",
            ),
            "evaluator": lambda: generate_evaluator_pairs(
                conn, count_per_subtask=EVALUATOR_PAIRS_PER_SUBTASK,
                outfile=PAIRS_DIR / "evaluator.jsonl",
            ),
            "evaluator_v2": lambda: generate_evaluator_pairs_v2(
                conn, count_per_subtask=EVALUATOR_V2_PAIRS_PER_SUBTASK,
                outfile=PAIRS_DIR / "evaluator_v2.jsonl",
            ),
        }
```

Also update the `--task` choices in the argparse block:

```python
    parser.add_argument(
        "--task",
        choices=["query_parser", "explainer", "evaluator", "evaluator_v2", "query_parser_v2", "all"],
        required=True,
        help="Which task to generate pairs for (use 'all' to run all tasks).",
    )
```

- [ ] **Step 3: Verify CLI help shows new tasks**

Run: `source .venv/bin/activate && python -m scripts.training.generate_training_pairs --help`
Expected: Shows `evaluator_v2` and `query_parser_v2` in choices

- [ ] **Step 4: Commit**

```bash
git add scripts/training/generate_training_pairs.py
git commit -m "feat(training): add evaluator v2 generator with perturbation pipeline (#139)"
```

---

### Task 7: Implement Query Parser v2 High-Level Generator

**Files:**
- Modify: `scripts/training/generate_training_pairs.py`

- [ ] **Step 1: Implement generate_query_parser_pairs_v2**

Add to `scripts/training/generate_training_pairs.py` after `generate_evaluator_pairs_v2`:

```python
from scripts.training.config import PARSER_V2_ENTITY_PAIRS
from scripts.training.prompts import ENTITY_TYPE_SEED_TABLES


def generate_query_parser_pairs_v2(
    conn: Any,
    count: int = PARSER_V2_ENTITY_PAIRS,
    outfile: Path | None = None,
) -> list[dict]:
    """Generate v2 query parser pairs targeting diverse entity types.

    Generates questions across 6 entity type categories using expanded seed
    tables and new templates.

    Args:
        conn: A live psycopg2 connection.
        count: Total number of pairs to generate across all entity types.
        outfile: Optional output path for incremental writes.

    Returns:
        A list of ChatML pair dicts.
    """
    # Load expanded seed data including new tables
    seed_rows: list[dict] = []
    for table in list(_ALLOWED_SEED_TABLES):
        try:
            seed_rows.extend(_fetch_seed_data(conn, table, limit=100))
        except Exception:  # noqa: BLE001
            continue
    if not seed_rows:
        seed_rows = _load_seed_rows(conn)
    random.shuffle(seed_rows)

    entity_types = list(ENTITY_TYPE_TEMPLATES.keys())
    # Distribute count across entity types per spec targets
    type_counts = {
        "organization": 50,
        "policy": 50,
        "sub_state_geography": 80,
        "intersectional": 40,
        "temporal": 30,
        "adversarial_json": 50,
    }
    # Scale if total count differs from 300
    total_specified = sum(type_counts.values())
    if count != total_specified:
        scale = count / total_specified
        type_counts = {k: max(1, round(v * scale)) for k, v in type_counts.items()}

    data_sources = list(_ALLOWED_SEED_TABLES)
    pairs: list[dict] = []

    fh = None
    if outfile is not None:
        outfile.parent.mkdir(parents=True, exist_ok=True)
        fh = outfile.open("w", encoding="utf-8")

    try:
        for entity_type, type_count in type_counts.items():
            questions = generate_query_parser_questions_v2(
                seed_rows, count=type_count, entity_type=entity_type,
            )
            for idx, q in enumerate(questions):
                if idx > 0 and idx % 25 == 0:
                    time.sleep(1)

                teacher_prompt = build_query_parser_prompt(
                    question=q["question"],
                    data_sources=data_sources,
                    question_style="adversarial" if entity_type == "adversarial_json" else "standard",
                )
                try:
                    response_text = _call_claude(D4BL_SYSTEM_PROMPT, teacher_prompt)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] Claude call failed for {entity_type} pair {idx}: {exc}", flush=True)
                    continue

                validated = _validate_json(response_text)
                if validated is None:
                    print(f"[warn] Invalid JSON for {entity_type} pair {idx}, skipping.", flush=True)
                    continue

                pair = format_as_chatml(
                    system=_STUDENT_QUERY_PARSER_SYSTEM,
                    user=q["question"],
                    assistant=json.dumps(validated, ensure_ascii=False),
                )
                pairs.append(pair)
                if fh is not None:
                    fh.write(json.dumps(pair, ensure_ascii=False) + "\n")
                    fh.flush()
                print(f"[query_parser_v2/{entity_type}] {len(pairs)} total pairs", flush=True)
    finally:
        if fh is not None:
            fh.close()
            print(f"[query_parser_v2] Saved {len(pairs)} pairs to {outfile}", flush=True)

    _print_cost_summary()
    return pairs
```

- [ ] **Step 2: Wire into the CLI task map**

In the `_TASK_MAP` dict in `main()`, add:

```python
            "query_parser_v2": lambda: generate_query_parser_pairs_v2(
                conn, count=PARSER_V2_ENTITY_PAIRS,
                outfile=PAIRS_DIR / "query_parser_v2.jsonl",
            ),
```

- [ ] **Step 3: Verify CLI shows the new task**

Run: `source .venv/bin/activate && python -m scripts.training.generate_training_pairs --help`
Expected: Shows `query_parser_v2` in choices

- [ ] **Step 4: Commit**

```bash
git add scripts/training/generate_training_pairs.py
git commit -m "feat(training): add query parser v2 generator with entity-type templates (#139)"
```

---

### Task 8: Update prepare_dataset.py with Glob Merge and Swap Augmentation

**Files:**
- Modify: `scripts/training/prepare_dataset.py`
- Create: `tests/test_training/test_prepare_dataset_v2.py`

- [ ] **Step 1: Write failing tests for glob merge and swap augmentation**

```python
# tests/test_training/test_prepare_dataset_v2.py
"""Tests for v2 prepare_dataset additions — glob merge and swap augmentation."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.training.prepare_dataset import (
    load_and_merge_pairs,
    apply_swap_augmentation,
)


def _make_pair(user: str, assistant: str, system: str = "sys") -> dict:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


class TestLoadAndMergePairs:
    def test_merges_two_files(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f2 = tmp_path / "evaluator_v2.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        f2.write_text(json.dumps(_make_pair("q2", '{"b":2}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 2

    def test_single_file_still_works(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 1

    def test_no_files_returns_empty(self, tmp_path: Path):
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert result == []

    def test_ignores_unrelated_files(self, tmp_path: Path):
        f1 = tmp_path / "evaluator.jsonl"
        f2 = tmp_path / "explainer.jsonl"
        f1.write_text(json.dumps(_make_pair("q1", '{"a":1}')) + "\n")
        f2.write_text(json.dumps(_make_pair("q2", '{"b":2}')) + "\n")
        result = load_and_merge_pairs(tmp_path, "evaluator")
        assert len(result) == 1


class TestApplySwapAugmentation:
    def test_doubles_pair_count(self):
        pairs = [_make_pair("Context:\ndata\n\nModel output:\nresponse", '{"score":3}')]
        result = apply_swap_augmentation(pairs)
        assert len(result) == 2

    def test_original_pair_preserved(self):
        original = _make_pair("Context:\ndata\n\nModel output:\nresponse", '{"score":3}')
        result = apply_swap_augmentation([original])
        assert result[0] == original

    def test_swapped_pair_has_reversed_sections(self):
        pairs = [_make_pair(
            "Context:\nthe context data\n\nModel output:\nthe model response",
            '{"score": 4}',
        )]
        result = apply_swap_augmentation(pairs)
        swapped_user = result[1]["messages"][1]["content"]
        # In swapped version, model output comes first
        assert swapped_user.index("Model output:") < swapped_user.index("Context:")

    def test_empty_input_returns_empty(self):
        assert apply_swap_augmentation([]) == []

    def test_pairs_without_separator_unchanged(self):
        pairs = [_make_pair("just a question", '{"score":3}')]
        result = apply_swap_augmentation(pairs)
        # No Context:/Model output: markers, so no swap possible — just return original
        assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prepare_dataset_v2.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement load_and_merge_pairs and apply_swap_augmentation**

Add to `scripts/training/prepare_dataset.py` after the existing `_load_pairs` function (around line 196):

```python
def load_and_merge_pairs(pairs_dir: Path, task_prefix: str) -> list[dict[str, Any]]:
    """Load and merge all JSONL files matching ``{task_prefix}*.jsonl`` in *pairs_dir*.

    This enables v1 + v2 data to be combined before dedup and splitting.

    Args:
        pairs_dir: Directory containing JSONL pair files.
        task_prefix: Prefix to match (e.g., "evaluator" matches "evaluator.jsonl"
            and "evaluator_v2.jsonl").

    Returns:
        Combined list of pairs from all matching files.
    """
    all_pairs: list[dict[str, Any]] = []
    pattern = f"{task_prefix}*.jsonl"
    matched_files = sorted(pairs_dir.glob(pattern))
    for path in matched_files:
        pairs = _load_pairs(path)
        print(f"[merge] Loaded {len(pairs)} pairs from {path.name}")
        all_pairs.extend(pairs)
    return all_pairs


def apply_swap_augmentation(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Duplicate evaluator pairs with swapped Context/Model output order.

    For each pair whose user message contains both "Context:" and "Model output:"
    sections, creates a copy with those sections swapped. This prevents position
    bias per JudgeLM (ICLR 2025).

    Args:
        pairs: List of ChatML-formatted evaluator pairs.

    Returns:
        Original pairs plus swapped copies (up to 2x input size).
    """
    if not pairs:
        return []

    result = list(pairs)
    separator = "\n\nModel output:\n"

    for pair in pairs:
        user_content = ""
        for msg in pair.get("messages", []):
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break

        if "Context:\n" not in user_content or separator not in user_content:
            continue

        # Split into context and model_output sections
        parts = user_content.split(separator, 1)
        if len(parts) != 2:
            continue

        context_section = parts[0]  # "Context:\n..."
        model_output_text = parts[1]

        # Remove "Context:\n" prefix for clean swap
        context_text = context_section.replace("Context:\n", "", 1)

        swapped_user = f"Model output:\n{model_output_text}\n\nContext:\n{context_text}"

        swapped_pair = {
            "messages": [
                pair["messages"][0],  # system prompt unchanged
                {"role": "user", "content": swapped_user},
                pair["messages"][2],  # assistant judgment unchanged
            ]
        }
        result.append(swapped_pair)

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prepare_dataset_v2.py -v`
Expected: All 10 tests PASSED

- [ ] **Step 5: Update process_task to use glob merge**

Replace the `process_task` function in `prepare_dataset.py`:

```python
def process_task(task: str) -> dict[str, int]:
    """Load, filter, deduplicate, and split training data for *task*.

    Uses glob-based merging to combine v1 + v2 pair files when both exist.
    Applies swap augmentation for evaluator relevance and bias subtasks.

    Args:
        task: Task name (e.g. ``"query_parser"``, ``"explainer"``).

    Returns:
        Dict mapping split name to number of examples written.
    """
    # Try glob merge first (combines task.jsonl + task_v2.jsonl etc.)
    pairs = load_and_merge_pairs(PAIRS_DIR, task)

    # Fall back to single file for backwards compatibility
    if not pairs:
        input_path = PAIRS_DIR / f"{task}.jsonl"
        if not input_path.exists():
            raise FileNotFoundError(f"No pairs files found for task: {task}")
        pairs = _load_pairs(input_path)
        print(f"[{task}] Loaded {len(pairs)} pairs from {input_path}")
    else:
        print(f"[{task}] Merged {len(pairs)} total pairs")

    pairs = filter_invalid_json(pairs)
    print(f"[{task}] After JSON filter: {len(pairs)} pairs")

    # Apply swap augmentation for evaluator (relevance + bias subtasks)
    if task == "evaluator":
        pre_swap = len(pairs)
        pairs = apply_swap_augmentation(pairs)
        print(f"[{task}] After swap augmentation: {len(pairs)} pairs (+{len(pairs) - pre_swap})")

    pairs = deduplicate_by_jaccard(pairs, threshold=JACCARD_THRESHOLD)
    print(f"[{task}] After deduplication: {len(pairs)} pairs")

    splits = split_dataset(pairs)

    counts: dict[str, int] = {}
    for split_name, split_pairs in splits.items():
        out_path = FINAL_DIR / task / f"{split_name}.jsonl"
        n = _write_split(split_pairs, out_path)
        counts[split_name] = n
        print(f"[{task}] Wrote {n} examples to {out_path}")

    return counts
```

- [ ] **Step 6: Run all prepare_dataset tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_prepare_dataset.py tests/test_training/test_prepare_dataset_v2.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add scripts/training/prepare_dataset.py tests/test_training/test_prepare_dataset_v2.py
git commit -m "feat(training): add glob merge and swap augmentation to prepare_dataset (#139)"
```

---

### Task 9: Expand _load_seed_rows with New Tables

**Files:**
- Modify: `scripts/training/generate_training_pairs.py`

- [ ] **Step 1: Update _load_seed_rows to include new tables**

In `scripts/training/generate_training_pairs.py`, modify the `_load_seed_rows` function (around line 417). Change the table list:

```python
def _load_seed_rows(conn: Any, limit: int = 200) -> list[dict]:
    """Fetch seed rows aggregated across all available tables.

    Attempts multiple tables and combines rows from all that are accessible.
    The combined list is shuffled before being truncated to *limit*.
    Falls back to a hardcoded sentinel row if none of the tables are available.

    Args:
        conn: A live psycopg2 connection.
        limit: Maximum number of rows to return in total.

    Returns:
        A list of row dicts (never empty).
    """
    fallback_row = {
        "geography_name": "Mississippi",
        "state_name": "Mississippi",
        "state_fips": "28",
        "metric": "median_household_income",
        "race": "black",
        "year": 2022,
        "value": 35400.0,
    }
    seed_tables = (
        "census_indicators",
        "cdc_health_outcomes",
        "census_demographics",
        "policy_bills",
        "bjs_incarceration",
        "vera_incarceration",
        "police_violence_incidents",
        "epa_environmental_justice",
    )
    rows: list[dict] = []
    for table in seed_tables:
        try:
            rows.extend(_fetch_seed_data(conn, table, limit=limit))
        except Exception:  # noqa: BLE001
            continue
    if rows:
        random.shuffle(rows)
        return rows[:limit]
    return [fallback_row]
```

- [ ] **Step 2: Verify the new tables are in the allowlist**

Check that `_ALLOWED_SEED_TABLES` (around line 108) already contains all the new tables. It should — the existing allowlist already has `policy_bills`, `bjs_incarceration`, `epa_environmental_justice`, `vera_incarceration`, and `police_violence_incidents`.

Run: `source .venv/bin/activate && python -c "from scripts.training.generate_training_pairs import _ALLOWED_SEED_TABLES; print(sorted(_ALLOWED_SEED_TABLES))"`
Expected: List includes all 5 new tables

- [ ] **Step 3: Run existing tests to verify no regressions**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/test_generate_pairs.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/training/generate_training_pairs.py
git commit -m "feat(training): expand seed data to include 5 new tables (#139)"
```

---

### Task 10: End-to-End Smoke Test (Manual Verification)

This task is a manual checkpoint — no code to write, just verification.

- [ ] **Step 1: Run all tests**

Run: `source .venv/bin/activate && python -m pytest tests/test_training/ -v --ignore=tests/test_training/test_integration_models.py --ignore=tests/test_training/test_regression.py`
Expected: All unit tests PASS

- [ ] **Step 2: Verify CLI shows all tasks**

Run: `source .venv/bin/activate && python -m scripts.training.generate_training_pairs --help`
Expected: Choices include `evaluator_v2` and `query_parser_v2`

- [ ] **Step 3: Verify prepare_dataset handles missing v2 files gracefully**

Run: `source .venv/bin/activate && python -c "from scripts.training.prepare_dataset import load_and_merge_pairs; from pathlib import Path; print(load_and_merge_pairs(Path('scripts/training_data/pairs'), 'evaluator'))"`
Expected: Loads existing evaluator.jsonl pairs without error

- [ ] **Step 4: Commit any final fixes**

If any issues were found, fix and commit:
```bash
git add -u
git commit -m "fix(training): address smoke test issues (#139)"
```

---

## Post-Implementation: Running the Expansion

**These steps require API keys and database access. They are NOT part of the code implementation.**

### Stage 1: Evaluator Expansion
```bash
export ANTHROPIC_API_KEY=your-key
python -m scripts.training.generate_training_pairs --task evaluator_v2
# Spot-check: review 30 hallucinated pairs in pairs/evaluator_v2.jsonl
# Verify schema compliance, hallucination realism, label correctness
python -m scripts.training.prepare_dataset --task evaluator
```

### Stage 2: Query Parser Expansion (after Stage 1 verified)
```bash
python -m scripts.training.generate_training_pairs --task query_parser_v2
# Spot-check: verify entity type coverage across 6 categories
python -m scripts.training.prepare_dataset --task query_parser
```
