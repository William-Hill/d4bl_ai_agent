"""Tests for v2 generator functions — pure functions only, no API calls."""

from __future__ import annotations

import json

from scripts.training.generate_training_pairs import (
    build_evaluator_v2_pair,
    build_hallucination_pair,
    generate_query_parser_questions_v2,
)
from scripts.training.prompts import STUDENT_EVALUATOR_SYSTEMS


class TestBuildHallucinationPair:
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

    def test_factual_pair_user_has_eval_framing(self):
        factual_pair, _ = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        user_content = factual_pair["messages"][1]["content"]
        assert user_content.startswith("Context:\n")
        assert "\n\nModel output:\n" in user_content
        assert self._FACTUAL in user_content

    def test_hallucinated_pair_user_has_eval_framing(self):
        _, hall_pair = build_hallucination_pair(
            self._SEED_ROW, self._FACTUAL, self._HALLUCINATED,
        )
        user_content = hall_pair["messages"][1]["content"]
        assert user_content.startswith("Context:\n")
        assert "\n\nModel output:\n" in user_content
        assert self._HALLUCINATED in user_content


class TestBuildEvaluatorV2Pair:
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

    def test_user_message_has_eval_framing(self):
        result = build_evaluator_v2_pair(
            subtask="relevance",
            seed_row=self._SEED_ROW,
            model_output=self._MODEL_OUTPUT,
            judgment=self._JUDGMENT,
        )
        user_content = result["messages"][1]["content"]
        assert user_content.startswith("Context:\n")
        assert "\n\nModel output:\n" in user_content
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
    _SEED_ROWS = [
        {"state": "Mississippi", "metric_name": "poverty_rate", "race": "Black", "year": 2022},
        {"state": "Alabama", "metric_name": "uninsured_rate", "race": "Hispanic", "year": 2021},
    ]

    def test_returns_requested_count(self):
        result = generate_query_parser_questions_v2(
            self._SEED_ROWS, count=5, entity_type="organization",
        )
        assert len(result) == 5

    def test_each_item_has_question_and_entity_type(self):
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
