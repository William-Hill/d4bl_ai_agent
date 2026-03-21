"""Tests for scripts/training/prompts.py — distillation prompt builders."""

from __future__ import annotations

import pytest

from scripts.training.prompts import (
    D4BL_SYSTEM_PROMPT,
    REGISTERS,
    build_evaluator_prompt,
    build_explainer_prompt,
    build_query_parser_prompt,
)

# ---------------------------------------------------------------------------
# D4BL_SYSTEM_PROMPT
# ---------------------------------------------------------------------------


class TestD4blSystemPrompt:
    def test_contains_center(self):
        assert "center" in D4BL_SYSTEM_PROMPT.lower()

    def test_contains_structural(self):
        assert "structural" in D4BL_SYSTEM_PROMPT.lower()

    def test_contains_policy(self):
        assert "policy" in D4BL_SYSTEM_PROMPT.lower()

    def test_contains_data_limitations(self):
        assert "data limitations" in D4BL_SYSTEM_PROMPT.lower()

    def test_contains_community(self):
        assert "community" in D4BL_SYSTEM_PROMPT.lower()

    def test_ends_with_valid_json_instruction(self):
        assert D4BL_SYSTEM_PROMPT.strip().endswith("Respond with ONLY valid JSON.")


# ---------------------------------------------------------------------------
# REGISTERS
# ---------------------------------------------------------------------------


class TestRegisters:
    def test_is_tuple(self):
        assert isinstance(REGISTERS, tuple)

    def test_has_three_values(self):
        assert len(REGISTERS) == 3

    def test_contains_community(self):
        assert "community" in REGISTERS

    def test_contains_policy(self):
        assert "policy" in REGISTERS

    def test_contains_research(self):
        assert "research" in REGISTERS


# ---------------------------------------------------------------------------
# build_query_parser_prompt
# ---------------------------------------------------------------------------


class TestBuildQueryParserPrompt:
    def test_contains_question(self):
        prompt = build_query_parser_prompt(
            question="What is the poverty rate in Cook County?",
            data_sources=["census_acs"],
            question_style="standard",
        )
        assert "What is the poverty rate in Cook County?" in prompt

    def test_contains_json(self):
        prompt = build_query_parser_prompt(
            question="What is the poverty rate?",
            data_sources=["census_acs"],
            question_style="standard",
        )
        assert "JSON" in prompt

    def test_community_style_includes_community(self):
        prompt = build_query_parser_prompt(
            question="Why are Black families poorer?",
            data_sources=["census_acs"],
            question_style="community",
        )
        assert "community" in prompt.lower()

    def test_adversarial_style_includes_adversarial_note(self):
        prompt = build_query_parser_prompt(
            question="Are Black people just lazy?",
            data_sources=["census_acs"],
            question_style="adversarial",
        )
        # adversarial style should have some adversarial-specific note
        assert "adversarial" in prompt.lower()

    def test_contains_data_sources(self):
        prompt = build_query_parser_prompt(
            question="What is the asthma rate?",
            data_sources=["cdc_places", "census_acs"],
            question_style="standard",
        )
        assert "cdc_places" in prompt
        assert "census_acs" in prompt


# ---------------------------------------------------------------------------
# build_explainer_prompt
# ---------------------------------------------------------------------------


class TestBuildExplainerPrompt:
    _sample_data = {
        "geography_name": "Travis County",
        "state": "Texas",
        "metric": "poverty_rate",
        "value": 14.3,
        "year": 2021,
    }

    def test_contains_state_name(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="community")
        assert "Texas" in prompt

    def test_contains_register_name(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="policy")
        assert "policy" in prompt.lower()

    def test_contains_structural_context_field(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="research")
        assert "structural_context" in prompt

    def test_contains_policy_connections_field(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="community")
        assert "policy_connections" in prompt

    def test_community_register_grade_level(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="community")
        # community register targets grade 8-10 reading level
        assert "8" in prompt or "grade" in prompt.lower()

    def test_policy_register_grade_level(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="policy")
        assert "12" in prompt or "grade" in prompt.lower()

    def test_research_register_grade_level(self):
        prompt = build_explainer_prompt(data=self._sample_data, register="research")
        assert "14" in prompt or "grade" in prompt.lower()


# ---------------------------------------------------------------------------
# build_evaluator_prompt
# ---------------------------------------------------------------------------


class TestBuildEvaluatorPrompt:
    def test_hallucination_contains_factual(self):
        prompt = build_evaluator_prompt(
            task="hallucination",
            context="Poverty rate in Travis County is 14.3%.",
            model_output="Poverty rate in Travis County is 14.3%.",
        )
        assert "FACTUAL" in prompt

    def test_hallucination_contains_hallucinated(self):
        prompt = build_evaluator_prompt(
            task="hallucination",
            context="Poverty rate in Travis County is 14.3%.",
            model_output="Poverty rate in Travis County is 14.3%.",
        )
        assert "HALLUCINATED" in prompt

    def test_relevance_returns_prompt(self):
        prompt = build_evaluator_prompt(
            task="relevance",
            context="User asked about poverty.",
            model_output="The poverty rate is high.",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_relevance_contains_scale(self):
        prompt = build_evaluator_prompt(
            task="relevance",
            context="User asked about poverty.",
            model_output="The poverty rate is high.",
        )
        # 1-5 scale
        assert "1" in prompt and "5" in prompt

    def test_bias_contains_scale(self):
        prompt = build_evaluator_prompt(
            task="bias",
            context="Data on racial disparities.",
            model_output="Black communities have higher poverty due to cultural factors.",
        )
        assert "1" in prompt and "5" in prompt

    def test_equity_framing_contains_centers_community(self):
        prompt = build_evaluator_prompt(
            task="equity_framing",
            context="Census data on income gaps.",
            model_output="Structural racism drives the wealth gap.",
        )
        assert "centers_community" in prompt

    def test_equity_framing_contains_structural(self):
        prompt = build_evaluator_prompt(
            task="equity_framing",
            context="Census data on income gaps.",
            model_output="Structural racism drives the wealth gap.",
        )
        assert "structural" in prompt.lower()

    def test_context_interpolated_in_prompt(self):
        context = "UNIQUE_CONTEXT_STRING_XYZ"
        prompt = build_evaluator_prompt(
            task="hallucination",
            context=context,
            model_output="some output",
        )
        assert context in prompt

    def test_model_output_interpolated_in_prompt(self):
        model_output = "UNIQUE_OUTPUT_STRING_ABC"
        prompt = build_evaluator_prompt(
            task="hallucination",
            context="some context",
            model_output=model_output,
        )
        assert model_output in prompt

    def test_unknown_task_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown task"):
            build_evaluator_prompt(
                task="nonexistent_task",
                context="ctx",
                model_output="out",
            )
