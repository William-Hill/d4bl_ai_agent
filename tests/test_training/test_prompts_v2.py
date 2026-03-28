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
