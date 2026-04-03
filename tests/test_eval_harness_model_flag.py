"""Tests for the --model flag in run_eval_harness.py."""

from __future__ import annotations

import pytest


class TestModelFlag:
    def test_model_flag_overrides_task_model(self):
        """When --model is provided, it should be used instead of TASK_MODELS[task]."""
        from scripts.training.run_eval_harness import TASK_MODELS, resolve_model_name

        # Without --model: uses default
        assert resolve_model_name(None, "query_parser") == TASK_MODELS["query_parser"]

        assert resolve_model_name(None, "evaluator") == TASK_MODELS["evaluator"]

        # With --model: uses override
        assert resolve_model_name("mistral", "query_parser") == "mistral"
        assert resolve_model_name("custom-model", "explainer") == "custom-model"

    def test_unknown_task_without_override_raises(self):
        """Without --model, unknown tasks should raise KeyError."""
        from scripts.training.run_eval_harness import resolve_model_name

        with pytest.raises(KeyError):
            resolve_model_name(None, "unknown_task")


class TestAnalyzeFlag:
    def test_parse_args_accepts_analyze(self):
        from scripts.training.run_eval_harness import build_parser

        args = build_parser().parse_args(["--task", "query_parser", "--persist", "--analyze"])
        assert args.analyze is True

    def test_parse_args_accepts_analyze_existing(self):
        from scripts.training.run_eval_harness import build_parser

        args = build_parser().parse_args(["--analyze-existing", "latest", "--task", "query_parser"])
        assert args.analyze_existing == "latest"

    def test_analyze_defaults_to_false(self):
        from scripts.training.run_eval_harness import build_parser

        args = build_parser().parse_args(["--task", "query_parser"])
        assert args.analyze is False

    def test_analyze_existing_defaults_to_none(self):
        from scripts.training.run_eval_harness import build_parser

        args = build_parser().parse_args(["--task", "query_parser"])
        assert args.analyze_existing is None