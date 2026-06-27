import json
import os
import hashlib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .domain import MissionGraph, MissionNode
from .graph import GraphValidator


@dataclass(frozen=True)
class JSONResponse:
    data: Dict[str, Any]
    total_tokens: int
    raw_usage: Dict[str, Any]
    response_attempts: int = 1


@dataclass(frozen=True)
class PlanningResult:
    graph: Optional[MissionGraph]
    first_pass_valid: bool
    revisions: int
    total_tokens: int
    validation_errors: Tuple[str, ...]
    cache_hit: bool = False
    api_response_retries: int = 0


class UrllibTransport:
    def post_json(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError("DeepSeek API HTTP %s: %s" % (exc.code, body[:500])) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("DeepSeek API connection failed: %s" % exc.reason) from exc


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
        transport: Optional[Any] = None,
        sleeper: Optional[Any] = None,
    ):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or UrllibTransport()
        self.sleeper = sleeper or time.sleep

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "DeepSeekClient":
        values: Dict[str, str] = {}
        path = Path(env_file) if env_file is not None else Path(".env")
        if path.exists():
            if path.stat().st_mode & 0o077:
                raise ValueError("%s contains credentials; run chmod 600 %s" % (path, path))
            for raw_line in path.read_text().splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                values[name.strip()] = value.strip().strip("'\"")
        key = os.environ.get("DEEPSEEK_API_KEY", values.get("DEEPSEEK_API_KEY", ""))
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is required; export a newly rotated key")
        return cls(
            api_key=key,
            model=os.environ.get("DEEPSEEK_MODEL", values.get("DEEPSEEK_MODEL", "deepseek-v4-flash")),
            base_url=os.environ.get(
                "DEEPSEEK_BASE_URL", values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            ),
            timeout=float(os.environ.get("DEEPSEEK_TIMEOUT", values.get("DEEPSEEK_TIMEOUT", "60"))),
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        response_retries: int = 2,
    ) -> JSONResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": max_tokens,
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        last_error = None
        for attempt in range(response_retries + 1):
            response = self.transport.post_json(
                self.base_url + "/chat/completions",
                {"Content-Type": "application/json", "Authorization": "Bearer " + self._api_key},
                payload,
                self.timeout,
            )
            try:
                content = response["choices"][0]["message"]["content"]
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise TypeError("JSON response is not an object")
                usage = response.get("usage", {})
                return JSONResponse(
                    data,
                    int(usage.get("total_tokens", 0)),
                    usage,
                    response_attempts=attempt + 1,
                )
            except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < response_retries:
                    self.sleeper(0.5 * (2 ** attempt))
        raise RuntimeError("DeepSeek returned an invalid JSON chat response") from last_error


class DeepSeekPlanner:
    SYSTEM_PROMPT = """You are the planner for a UAV mission research simulator.
Output json only. Convert the user instruction into a mission graph object with:
reserve_ratio and nodes. Each node has id, kind, dependencies, metadata,
required, failure_target. Supported kinds: takeoff, move, inspect, return,
land, recover, report, human_confirm. Every flight execution node needs failure_target
\"recover\". Include a recover node with required=false and failure_target=null.
If takeoff exists, include return and use reserve_ratio >= 0.25.
Every move node needs metadata.waypoint, inspect/capture needs metadata.target,
and return needs numeric metadata.distance.
Example json: {"reserve_ratio":0.25,"nodes":[
{"id":"takeoff","kind":"takeoff","dependencies":[],"metadata":{"altitude_m":12},"failure_target":"recover"},
{"id":"recover","kind":"recover","dependencies":[],"metadata":{},"required":false,"failure_target":null},
{"id":"return","kind":"return","dependencies":["takeoff"],"metadata":{"distance":10},"failure_target":"recover"}
]}"""

    PROMPT_VERSION = "cmg-v4"

    def __init__(
        self,
        client: DeepSeekClient,
        max_revisions: int = 2,
        cache_dir: Optional[Path] = None,
    ):
        self.client = client
        self.max_revisions = max_revisions
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None

    def plan(self, instruction: str, mission_id: str) -> MissionGraph:
        result = self.plan_detailed(instruction, mission_id)
        if result.graph is None:
            raise ValueError("invalid DeepSeek mission graph: %s" % "; ".join(result.validation_errors))
        return result.graph

    def plan_detailed(
        self,
        instruction: str,
        mission_id: str,
        additional_validator: Optional[Callable[[MissionGraph], Tuple[str, ...]]] = None,
        validation_version: str = "structural",
    ) -> PlanningResult:
        cached = self._load_cache(
            instruction, mission_id, additional_validator, validation_version
        )
        if cached is not None:
            return cached
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": "Mission: " + instruction + "\nReturn json."},
        ]
        total_tokens = 0
        api_response_retries = 0
        first_pass_valid = False
        last_errors: Tuple[str, ...] = ()
        for attempt in range(self.max_revisions + 1):
            response = self.client.chat_json(messages)
            total_tokens += response.total_tokens
            api_response_retries += response.response_attempts - 1
            graph, errors = self._parse_and_validate(response.data, mission_id)
            if graph is not None and additional_validator is not None:
                semantic_errors = tuple(additional_validator(graph))
                if semantic_errors:
                    graph = None
                    errors = semantic_errors
            if graph is not None:
                first_pass_valid = attempt == 0
                result = PlanningResult(
                    graph=graph,
                    first_pass_valid=first_pass_valid,
                    revisions=attempt,
                    total_tokens=total_tokens,
                    validation_errors=last_errors,
                    api_response_retries=api_response_retries,
                )
                self._save_cache(instruction, mission_id, result, validation_version)
                return result
            last_errors = errors
            if attempt < self.max_revisions:
                messages.append({"role": "assistant", "content": json.dumps(response.data, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": "Validation errors: %s. Repair the graph and return the complete corrected json."
                        % "; ".join(errors),
                    }
                )
        result = PlanningResult(
            None,
            False,
            self.max_revisions,
            total_tokens,
            last_errors,
            api_response_retries=api_response_retries,
        )
        self._save_cache(instruction, mission_id, result, validation_version)
        return result

    def repair_detailed(
        self,
        instruction: str,
        mission_id: str,
        initial_graph: MissionGraph,
        initial_errors: Tuple[str, ...],
        additional_validator: Callable[[MissionGraph], Tuple[str, ...]],
        validation_version: str,
    ) -> PlanningResult:
        cached = self._load_cache(
            instruction, mission_id, additional_validator, validation_version
        )
        if cached is not None:
            return cached
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": "Mission: " + instruction + "\nReturn json."},
            {
                "role": "assistant",
                "content": json.dumps(self._graph_to_data(initial_graph), ensure_ascii=False),
            },
            {
                "role": "user",
                "content": "Validation errors: %s. Repair the graph and return the complete corrected json."
                % "; ".join(initial_errors),
            },
        ]
        total_tokens = 0
        api_response_retries = 0
        last_errors = initial_errors
        for revision in range(1, self.max_revisions + 1):
            response = self.client.chat_json(messages)
            total_tokens += response.total_tokens
            api_response_retries += response.response_attempts - 1
            graph, errors = self._parse_and_validate(response.data, mission_id)
            if graph is not None:
                semantic_errors = tuple(additional_validator(graph))
                if semantic_errors:
                    graph = None
                    errors = semantic_errors
            if graph is not None:
                result = PlanningResult(
                    graph,
                    False,
                    revision,
                    total_tokens,
                    last_errors,
                    api_response_retries=api_response_retries,
                )
                self._save_cache(instruction, mission_id, result, validation_version)
                return result
            last_errors = errors
            if revision < self.max_revisions:
                messages.append({"role": "assistant", "content": json.dumps(response.data, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": "Validation errors: %s. Repair every missing constraint and return complete json."
                        % "; ".join(errors),
                    }
                )
        result = PlanningResult(
            None,
            False,
            self.max_revisions,
            total_tokens,
            tuple(last_errors),
            api_response_retries=api_response_retries,
        )
        self._save_cache(instruction, mission_id, result, validation_version)
        return result

    @staticmethod
    def _graph_to_data(graph: MissionGraph) -> Dict[str, Any]:
        return {
            "reserve_ratio": graph.reserve_ratio,
            "nodes": [
                {
                    "id": node.id,
                    "kind": node.kind,
                    "dependencies": list(node.dependencies),
                    "failure_target": node.failure_target,
                    "risk": node.risk,
                    "required": node.required,
                    "metadata": node.metadata,
                }
                for node in graph.nodes
            ],
        }

    @staticmethod
    def _parse_and_validate(
        data: Dict[str, Any], mission_id: str
    ) -> Tuple[Optional[MissionGraph], Tuple[str, ...]]:
        try:
            nodes = tuple(
                MissionNode(
                    id=str(item["id"]),
                    kind=str(item["kind"]),
                    dependencies=tuple(item.get("dependencies", ())),
                    failure_target=item.get("failure_target", "recover"),
                    risk=str(item.get("risk", "low")),
                    required=bool(item.get("required", True)),
                    metadata=dict(item.get("metadata", {})),
                )
                for item in data["nodes"]
            )
            graph = MissionGraph(
                mission_id=mission_id,
                nodes=nodes,
                reserve_ratio=float(data.get("reserve_ratio", 0.25)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return None, ("invalid DeepSeek mission graph schema: %s" % exc,)
        report = GraphValidator().validate(graph)
        if not report.valid:
            return None, report.errors
        return graph, ()

    def _cache_path(
        self, instruction: str, mission_id: str, validation_version: str = "structural"
    ) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        material = "\n".join(
            (self.client.model, self.PROMPT_VERSION, validation_version, mission_id, instruction)
        )
        return self.cache_dir / (hashlib.sha256(material.encode("utf-8")).hexdigest() + ".json")

    def _legacy_cache_path(self, instruction: str, mission_id: str) -> Optional[Path]:
        if self.cache_dir is None:
            return None
        material = "\n".join((self.client.model, self.PROMPT_VERSION, mission_id, instruction))
        return self.cache_dir / (hashlib.sha256(material.encode("utf-8")).hexdigest() + ".json")

    def _load_cache(
        self,
        instruction: str,
        mission_id: str,
        additional_validator: Optional[Callable[[MissionGraph], Tuple[str, ...]]] = None,
        validation_version: str = "structural",
    ) -> Optional[PlanningResult]:
        path = self._cache_path(instruction, mission_id, validation_version)
        if path is not None and not path.exists() and validation_version == "structural":
            legacy_path = self._legacy_cache_path(instruction, mission_id)
            if legacy_path is not None and legacy_path.exists():
                path = legacy_path
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text())
        graph_data = data.get("graph")
        graph = None
        if graph_data is not None:
            graph, errors = self._parse_and_validate(graph_data, mission_id)
            if graph is None:
                return None
            if additional_validator is not None and additional_validator(graph):
                return None
        return PlanningResult(
            graph=graph,
            first_pass_valid=bool(data["first_pass_valid"]),
            revisions=int(data["revisions"]),
            total_tokens=int(data["total_tokens"]),
            validation_errors=tuple(data.get("validation_errors", ())),
            cache_hit=True,
            api_response_retries=int(data.get("api_response_retries", 0)),
        )

    def _save_cache(
        self,
        instruction: str,
        mission_id: str,
        result: PlanningResult,
        validation_version: str = "structural",
    ) -> None:
        path = self._cache_path(instruction, mission_id, validation_version)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        graph_data = None
        if result.graph is not None:
            graph_data = self._graph_to_data(result.graph)
        payload = {
            "prompt_version": self.PROMPT_VERSION,
            "validation_version": validation_version,
            "model": self.client.model,
            "graph": graph_data,
            "first_pass_valid": result.first_pass_valid,
            "revisions": result.revisions,
            "total_tokens": result.total_tokens,
            "validation_errors": list(result.validation_errors),
            "api_response_retries": result.api_response_retries,
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
