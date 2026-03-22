"""Test that the evaluation runner uses the task-specific evaluator model."""
from unittest.mock import MagicMock, patch


class TestRunnerModelRouting:
    @patch("d4bl.services.langfuse.runner.get_llm_for_task")
    @patch("d4bl.services.langfuse.runner.get_langfuse_eval_client")
    def test_runner_calls_get_llm_for_task(self, mock_langfuse, mock_get_task_llm):
        """run_comprehensive_evaluation() should call get_llm_for_task('evaluator')."""
        from d4bl.services.langfuse.runner import run_comprehensive_evaluation

        mock_langfuse.return_value = None  # Skip Langfuse (returns SKIPPED)
        mock_get_task_llm.return_value = MagicMock()

        run_comprehensive_evaluation(
            query="test", research_output="test output", sources=[]
        )

        mock_get_task_llm.assert_called_once_with("evaluator")
