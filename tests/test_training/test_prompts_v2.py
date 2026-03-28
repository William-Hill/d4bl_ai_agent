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
