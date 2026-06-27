import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text())


def test_story_is_chronological_and_ends_with_report():
    story = load_json("demos/data/agriculture_story.json")
    times = [event["time"] for event in story["events"]]

    assert story["duration"] == 90
    assert times == sorted(times)
    assert story["events"][-1]["type"] == "report"


def test_story_contains_required_recovery_narrative():
    story = load_json("demos/data/agriculture_story.json")
    event_types = {event["type"] for event in story["events"]}

    assert {"tool", "detection", "fault", "recovery", "report"} <= event_types
    assert len(story["graph"]["nodes"]) == 8


def test_demo_agentfly_metrics_match_checked_in_mvp_summary():
    demo = load_json("demos/data/research_results.json")
    source = load_json("outputs/mvp/summary.json")
    expected = source["metrics"]["agentfly"]
    actual = next(row for row in demo["mock_benchmark"] if row["method"] == "AgentFly")

    assert actual["task_success_rate"] == expected["task_success_rate"]
    assert actual["recovery_success_rate"] == expected["recovery_success_rate"]


def test_demo_shell_has_required_accessible_controls():
    html = (ROOT / "demos/index.html").read_text()

    for control in ('id="play-toggle"', 'id="restart"', 'id="speed"', 'id="chapter-nav"'):
        assert control in html
    assert 'aria-live="polite"' in html
    assert 'viewBox="0 0 1000 620"' in html


def test_demo_css_preserves_hidden_attribute_behavior():
    css = (ROOT / "demos/styles.css").read_text()

    assert "[hidden]" in css
    assert "display: none !important" in css
