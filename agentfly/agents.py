from dataclasses import replace
from typing import Optional

from .domain import MissionNode
from .tools import ToolCall, ToolResult


class AgentPolicy:
    name = "base"

    def recover(
        self, node: MissionNode, failed_call: ToolCall, result: ToolResult, attempt: int
    ) -> Optional[ToolCall]:
        return None


class AgentFlyPolicy(AgentPolicy):
    name = "agentfly"

    def recover(
        self, node: MissionNode, failed_call: ToolCall, result: ToolResult, attempt: int
    ) -> Optional[ToolCall]:
        if result.code == "waypoint_unreachable" and node.metadata.get("alternate") and attempt == 1:
            arguments = dict(failed_call.arguments)
            arguments["waypoint"] = node.metadata["alternate"]
            return replace(
                failed_call,
                arguments=arguments,
                idempotency_key=failed_call.idempotency_key + "-repair",
            )
        return None


class NoRecoveryPolicy(AgentPolicy):
    name = "no_recovery"


class RulePolicy(AgentPolicy):
    name = "rule"

    def recover(self, node, failed_call, result, attempt):
        if result.code == "waypoint_unreachable" and node.metadata.get("known_rule"):
            arguments = dict(failed_call.arguments)
            arguments["waypoint"] = node.metadata["alternate"]
            return replace(failed_call, arguments=arguments, idempotency_key=failed_call.idempotency_key + "-rule")
        return None


class ReActPolicy(AgentPolicy):
    name = "react"

    def recover(self, node, failed_call, result, attempt):
        if attempt == 1:
            return replace(failed_call, idempotency_key=failed_call.idempotency_key + "-retry")
        return None


class PDDLPolicy(NoRecoveryPolicy):
    name = "pddl"


class PureLLMPolicy(NoRecoveryPolicy):
    name = "pure_llm"
