from typing import Dict, List, Set

from .domain import MissionGraph, ValidationReport


class GraphValidator:
    EXECUTION_KINDS = {"takeoff", "inspect", "capture", "move", "return", "land"}
    ALLOWED_KINDS = EXECUTION_KINDS | {"recover", "report", "human_confirm"}
    REQUIRED_METADATA = {
        "move": "waypoint",
        "inspect": "target",
        "capture": "target",
        "return": "distance",
    }

    def validate(self, graph: MissionGraph) -> ValidationReport:
        errors: List[str] = []
        nodes = graph.by_id()
        if len(nodes) != len(graph.nodes):
            errors.append("duplicate node id")
        for node in graph.nodes:
            if node.kind not in self.ALLOWED_KINDS:
                errors.append("unsupported node kind %s for %s" % (node.kind, node.id))
            for dependency in node.dependencies:
                if dependency not in nodes:
                    errors.append("missing dependency %s for %s" % (dependency, node.id))
            if node.kind in self.EXECUTION_KINDS and not node.failure_target:
                errors.append("missing failure route for %s" % node.id)
            if node.failure_target and node.failure_target not in nodes:
                errors.append("missing failure target %s for %s" % (node.failure_target, node.id))
            required_field = self.REQUIRED_METADATA.get(node.kind)
            if required_field and required_field not in node.metadata:
                errors.append(
                    "%s requires metadata.%s for %s" % (node.kind, required_field, node.id)
                )
        if self._has_cycle(graph):
            errors.append("cycle detected")
        if any(node.kind == "takeoff" for node in graph.nodes):
            if not any(node.kind == "return" for node in graph.nodes):
                errors.append("takeoff graph requires return node")
            if graph.reserve_ratio < 0.25:
                errors.append("reserve ratio must be at least 0.25")
        return ValidationReport(tuple(errors))

    @staticmethod
    def _has_cycle(graph: MissionGraph) -> bool:
        nodes = graph.by_id()
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited or node_id not in nodes:
                return False
            visiting.add(node_id)
            for dependency in nodes[node_id].dependencies:
                if visit(dependency):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node_id) for node_id in nodes)
