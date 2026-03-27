"""Tests for the --model flag in run_eval_harness.py."""
from __future__ import annotations

import pytest


class TestModelFlag:
    def test_model_flag_overrides_task_model(self):
        """When --model is provided, it should be used instead of TASK_MODELS[task]."""
        from scripts.training.run_eval_harness import resolve_model_name, TASK_MODELS

        # Without --model: uses default
        assert resolve_model_name(None, "query_parser") == TASK_MODELS["query_parser"]

        # With --model: uses override
        assert resolve_model_name("mistral", "query_parser") == "mistral"
        assert resolve_model_name("custom-model", "explainer") == "custom-model"
