"""Tests for v3 training pair generation: document-sourced evaluator pairs
and community_framing parser pairs."""

import json

from scripts.training.generate_training_pairs import (
    build_doc_hallucination_pair,
    build_community_framing_pair,
    format_as_chatml,
    format_eval_user_message,
)


class TestBuildDocHallucinationPair:
    def test_returns_factual_and_hallucinated(self):
        chunk = {
            "content": "In 2023, Georgia had an eviction rate of 5.2%.",
            "title": "Housing Report",
            "content_type": "research_report",
        }
        hallucinated_text = "In 2023, Georgia had an eviction rate of 12.8%."
        factual_pair, hall_pair = build_doc_hallucination_pair(chunk, hallucinated_text)

        assert "messages" in factual_pair
        assert "messages" in hall_pair
        assert len(factual_pair["messages"]) == 3
        assert len(hall_pair["messages"]) == 3

        factual_label = json.loads(factual_pair["messages"][2]["content"])
        assert factual_label["label"] == "FACTUAL"

        hall_label = json.loads(hall_pair["messages"][2]["content"])
        assert hall_label["label"] == "HALLUCINATED"

    def test_context_contains_chunk_content(self):
        chunk = {
            "content": "Specific eviction data here.",
            "title": "Report",
            "content_type": "policy_bill",
        }
        factual_pair, _ = build_doc_hallucination_pair(chunk, "Fake data.")
        user_msg = factual_pair["messages"][1]["content"]
        assert "Specific eviction data here." in user_msg


class TestBuildCommunityFramingPair:
    def test_returns_chatml_with_community_framing(self):
        question = "Our community is fighting eviction rates — what does HB 432 do?"
        expected_framing = {
            "detected": True,
            "issue_domain": "housing",
            "structural_frame": "economic_displacement",
        }
        pair = build_community_framing_pair(
            question=question,
            entities=["Georgia"],
            data_sources=["census_indicators", "policy_bills"],
            community_framing=expected_framing,
        )
        assert "messages" in pair
        assert len(pair["messages"]) == 3

        assistant_json = json.loads(pair["messages"][2]["content"])
        assert assistant_json["community_framing"]["detected"] is True
        assert assistant_json["community_framing"]["issue_domain"] == "housing"

    def test_user_message_is_the_question(self):
        pair = build_community_framing_pair(
            question="Why are people being pushed out?",
            entities=["Atlanta"],
            data_sources=["census_indicators"],
            community_framing={"detected": True, "issue_domain": "housing",
                               "structural_frame": "gentrification"},
        )
        assert pair["messages"][1]["content"] == "Why are people being pushed out?"
