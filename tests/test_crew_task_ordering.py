"""Tests that selected agent task ordering is deterministic and sequential."""
import sys

sys.path.insert(0, 'src')
from d4bl.agents.crew import D4Bl


def _get_ordered_task_names(selected_agents: list) -> list:
    """Return the task names that would run for the given selected agents, in order."""
    selected_task_names = {
        D4Bl.AGENT_TASK_MAP[name]
        for name in selected_agents
        if name in D4Bl.AGENT_TASK_MAP
    }
    return [t for t in D4Bl.TASK_ORDER if t in selected_task_names]


def test_researcher_before_analyst():
    names = _get_ordered_task_names(["researcher", "data_analyst"])
    assert "research_task" in names
    assert "analysis_task" in names
    assert names.index("research_task") < names.index("analysis_task")


def test_analyst_before_writer():
    names = _get_ordered_task_names(["data_analyst", "writer"])
    assert names.index("analysis_task") < names.index("writing_task")


def test_single_agent_returns_one_task():
    names = _get_ordered_task_names(["researcher"])
    assert names == ["research_task"]


def test_all_agents_full_canonical_order():
    import sys
    sys.path.insert(0, 'src')
    from d4bl.agents.crew import D4Bl
    all_agents = list(D4Bl.AGENT_TASK_MAP.keys())
    names = _get_ordered_task_names(all_agents)
    assert names == D4Bl.TASK_ORDER
