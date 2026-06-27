import json

import pytest

from agentfly.cli import plan_with_deepseek
from agentfly.deepseek import DeepSeekClient, DeepSeekPlanner
from agentfly.domain import MissionGraph, MissionNode


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.request = None

    def post_json(self, url, headers, payload, timeout):
        self.request = (url, headers, payload, timeout)
        return self.response


class SequenceTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post_json(self, url, headers, payload, timeout):
        self.requests.append((url, headers, payload, timeout))
        return self.responses.pop(0)


def test_client_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekClient.from_env(env_file=tmp_path / "missing.env")


def test_client_loads_key_from_private_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=file-secret\nDEEPSEEK_MODEL=deepseek-v4-pro\n")
    env_file.chmod(0o600)
    client = DeepSeekClient.from_env(env_file=env_file)
    assert client.model == "deepseek-v4-pro"


def test_client_rejects_world_readable_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=file-secret\n")
    env_file.chmod(0o644)
    with pytest.raises(ValueError, match="chmod 600"):
        DeepSeekClient.from_env(env_file=env_file)


def test_client_uses_current_endpoint_model_and_json_mode():
    transport = FakeTransport(
        {"choices": [{"message": {"content": json.dumps({"nodes": []})}}], "usage": {"total_tokens": 8}}
    )
    client = DeepSeekClient("secret-test-key", transport=transport)
    result = client.chat_json([{"role": "user", "content": "output json"}])
    url, headers, payload, timeout = transport.request
    assert url == "https://api.deepseek.com/chat/completions"
    assert headers["Authorization"] == "Bearer secret-test-key"
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["temperature"] == 0
    assert payload["thinking"] == {"type": "disabled"}
    assert result.data == {"nodes": []}
    assert result.total_tokens == 8


def test_client_retries_empty_json_content_before_failing():
    valid = {"nodes": []}
    transport = SequenceTransport(
        [
            {"choices": [{"message": {"content": ""}}]},
            {"choices": [{"message": {"content": json.dumps(valid)}}], "usage": {"total_tokens": 7}},
        ]
    )
    sleeps = []
    client = DeepSeekClient("key", transport=transport, sleeper=sleeps.append)
    response = client.chat_json([{"role": "user", "content": "json"}], response_retries=1)
    assert response.data == valid
    assert response.response_attempts == 2
    assert sleeps == [0.5]


def test_planner_converts_deepseek_json_to_valid_mission_graph():
    content = {
        "reserve_ratio": 0.3,
        "nodes": [
            {"id": "takeoff", "kind": "takeoff", "dependencies": [], "metadata": {"altitude_m": 12}},
            {"id": "return", "kind": "return", "dependencies": ["takeoff"], "metadata": {"distance": 10}},
            {"id": "recover", "kind": "recover", "dependencies": [], "required": False, "failure_target": None},
        ],
    }
    transport = FakeTransport({"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}})
    graph = DeepSeekPlanner(DeepSeekClient("key", transport=transport)).plan("巡检 A 区", "deepseek-1")
    assert graph.mission_id == "deepseek-1"
    assert graph.reserve_ratio == 0.3
    assert [node.id for node in graph.nodes] == ["takeoff", "return", "recover"]


def test_planner_rejects_invalid_generated_graph():
    content = {"reserve_ratio": 0.1, "nodes": [{"id": "takeoff", "kind": "takeoff"}]}
    transport = FakeTransport({"choices": [{"message": {"content": json.dumps(content)}}]})
    with pytest.raises(ValueError, match="invalid DeepSeek mission graph"):
        DeepSeekPlanner(DeepSeekClient("key", transport=transport), max_revisions=0).plan("起飞", "bad")


def test_planner_repairs_invalid_graph_using_validator_feedback():
    invalid = {"reserve_ratio": 0.1, "nodes": [{"id": "takeoff", "kind": "takeoff"}]}
    valid = {
        "reserve_ratio": 0.25,
        "nodes": [
            {"id": "takeoff", "kind": "takeoff", "failure_target": "recover"},
            {"id": "return", "kind": "return", "dependencies": ["takeoff"], "failure_target": "recover", "metadata": {"distance": 10}},
            {"id": "recover", "kind": "recover", "required": False, "failure_target": None},
        ],
    }
    transport = SequenceTransport(
        [
            {"choices": [{"message": {"content": json.dumps(invalid)}}], "usage": {"total_tokens": 10}},
            {"choices": [{"message": {"content": json.dumps(valid)}}], "usage": {"total_tokens": 12}},
        ]
    )
    planner = DeepSeekPlanner(DeepSeekClient("key", transport=transport), max_revisions=1)
    result = planner.plan_detailed("执行巡检", "repair-1")
    assert result.graph is not None
    assert not result.first_pass_valid
    assert result.revisions == 1
    assert result.total_tokens == 22
    assert result.api_response_retries == 0
    assert "Validation errors" in transport.requests[1][2]["messages"][-1]["content"]


def test_planner_cache_prevents_duplicate_api_calls(tmp_path):
    valid = {
        "reserve_ratio": 0.25,
        "nodes": [{"id": "recover", "kind": "recover", "required": False, "failure_target": None}],
    }
    transport = SequenceTransport(
        [{"choices": [{"message": {"content": json.dumps(valid)}}], "usage": {"total_tokens": 5}}]
    )
    planner = DeepSeekPlanner(DeepSeekClient("key", transport=transport), cache_dir=tmp_path)
    first = planner.plan_detailed("缓存任务", "cache-1")
    second = planner.plan_detailed("缓存任务", "cache-1")
    assert first.graph == second.graph
    assert second.cache_hit
    assert len(transport.requests) == 1


def test_planner_repairs_additional_semantic_validation_error():
    first = {
        "reserve_ratio": 0.25,
        "nodes": [{"id": "recover", "kind": "recover", "required": False, "failure_target": None}],
    }
    second = {
        "reserve_ratio": 0.25,
        "nodes": [
            {"id": "move", "kind": "move", "metadata": {"waypoint": "A", "avoid_zone": "west"}},
            {"id": "recover", "kind": "recover", "required": False, "failure_target": None},
        ],
    }
    transport = SequenceTransport(
        [
            {"choices": [{"message": {"content": json.dumps(first)}}]},
            {"choices": [{"message": {"content": json.dumps(second)}}]},
        ]
    )

    def require_geofence(graph):
        return () if any("avoid_zone" in node.metadata for node in graph.nodes) else ("missing geofence grounding",)

    result = DeepSeekPlanner(DeepSeekClient("key", transport=transport), max_revisions=1).plan_detailed(
        "避开西侧禁飞区", "semantic-1", additional_validator=require_geofence, validation_version="semantic-v1"
    )
    assert result.graph is not None
    assert result.revisions == 1
    assert not result.first_pass_valid


def test_repair_detailed_starts_from_existing_graph_without_regeneration():
    initial = MissionGraph(
        "repair-existing",
        (MissionNode("recover", "recover", required=False, failure_target=None),),
        0.25,
    )
    repaired = {
        "reserve_ratio": 0.25,
        "nodes": [
            {"id": "move", "kind": "move", "metadata": {"waypoint": "A", "privacy_zone": "west"}},
            {"id": "recover", "kind": "recover", "required": False, "failure_target": None},
        ],
    }
    transport = SequenceTransport(
        [{"choices": [{"message": {"content": json.dumps(repaired)}}], "usage": {"total_tokens": 9}}]
    )
    planner = DeepSeekPlanner(DeepSeekClient("key", transport=transport), max_revisions=2)

    def require_privacy(graph):
        return () if any("privacy_zone" in node.metadata for node in graph.nodes) else ("missing privacy zone",)

    result = planner.repair_detailed(
        "避开隐私区",
        "repair-existing",
        initial,
        ("missing privacy zone",),
        require_privacy,
        "constraint-v1",
    )
    assert result.graph is not None
    assert result.revisions == 1
    assert len(transport.requests) == 1


def test_plan_command_helper_writes_generated_graph(tmp_path):
    class FakePlanner:
        def plan(self, instruction, mission_id):
            content = {
                "reserve_ratio": 0.25,
                "nodes": [
                    {"id": "recover", "kind": "recover", "required": False, "failure_target": None}
                ],
            }
            transport = FakeTransport({"choices": [{"message": {"content": json.dumps(content)}}]})
            return DeepSeekPlanner(DeepSeekClient("key", transport=transport)).plan(instruction, mission_id)

    output = tmp_path / "mission.json"
    saved = plan_with_deepseek("巡检 A 区", "m-cli", output, planner=FakePlanner())
    assert output.exists()
    assert saved["mission_id"] == "m-cli"
    assert saved["nodes"][0]["kind"] == "recover"
