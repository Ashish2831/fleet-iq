from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


def json_safe(value, *, depth=0):
    if depth > 6:
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): json_safe(v, depth=depth + 1) for k, v in list(value.items())[:24]}
    if isinstance(value, (list, tuple)):
        return [json_safe(v, depth=depth + 1) for v in value[:20]]
    return value


@dataclass
class ToolContext:
    tenant: object
    user: object
    traces: list = field(default_factory=list)
    calls: int = 0
    max_calls: int = 12

    def log(self, node: str, tool: str, args: dict, result):
        preview = result
        if isinstance(result, dict):
            preview = {k: result[k] for k in list(result)[:12]}
        elif isinstance(result, list):
            preview = result[:5]
        self.traces.append(
            {"node": node, "tool": tool, "args": json_safe(args), "result": json_safe(preview)}
        )
