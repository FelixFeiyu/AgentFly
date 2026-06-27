from dataclasses import dataclass, field
from typing import Any, Dict

from .environment import EnvironmentResult, MockUAVEnvironment


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Dict[str, Any]
    idempotency_key: str


@dataclass(frozen=True)
class ToolResult:
    success: bool
    code: str
    data: Dict[str, Any] = field(default_factory=dict)


class SafetyGate:
    def __init__(self, reserve_ratio: float = 0.25):
        self.reserve_ratio = reserve_ratio

    def evaluate(self, call: ToolCall, env: MockUAVEnvironment) -> ToolResult:
        if call.name == "takeoff" and env.battery_ratio < self.reserve_ratio:
            return ToolResult(False, "safety_rejected", {"reason": "insufficient_reserve"})
        if call.name == "move" and not call.arguments.get("in_geofence", True):
            return ToolResult(False, "safety_rejected", {"reason": "geofence"})
        if call.name in {"move", "inspect", "return", "land"} and not env.airborne:
            return ToolResult(False, "safety_rejected", {"reason": "not_airborne"})
        return ToolResult(True, "allowed")


class ToolManager:
    def __init__(self, env: MockUAVEnvironment, safety_gate: SafetyGate):
        self.env = env
        self.safety_gate = safety_gate
        self._cache: Dict[str, ToolResult] = {}

    def invoke(self, call: ToolCall) -> ToolResult:
        if call.idempotency_key in self._cache:
            return self._cache[call.idempotency_key]
        safety = self.safety_gate.evaluate(call, self.env)
        if not safety.success:
            self._cache[call.idempotency_key] = safety
            return safety
        result: EnvironmentResult = self.env.execute(call.name, call.arguments)
        tool_result = ToolResult(result.success, result.code, result.data)
        self._cache[call.idempotency_key] = tool_result
        return tool_result
