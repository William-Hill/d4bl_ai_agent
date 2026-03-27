"""Tests for model comparison endpoint schemas and behavior."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from d4bl.app.schemas import CompareRequest


class TestCompareRequest:
    def test_valid_request(self):
        r = CompareRequest(prompt="What is poverty rate?", task="query_parser")
        assert r.prompt == "What is poverty rate?"
        assert r.task == "query_parser"

    def test_blank_prompt_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(prompt="", task="query_parser")

    def test_invalid_task_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(prompt="test", task="invalid_task")
