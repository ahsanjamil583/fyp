from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AgentToolEvent:
    """Small serializable trace event for every tool/agent step.

    The trace is intentionally high level. It is useful for the owner dashboard,
    debugging, and FYP evaluation without exposing private chain-of-thought.
    """

    agent: str
    tool: str
    status: str = "success"
    summary: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    startedAt: str = field(default_factory=utc_now_iso)
    endedAt: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "input": self.input,
            "output": self.output,
            "startedAt": self.startedAt,
            "endedAt": self.endedAt,
        }


@dataclass
class AgentRunState:
    tenant: dict[str, Any]
    userMessage: str
    recentMessages: list[dict[str, Any]] = field(default_factory=list)
    channel: str = "customer_portal"
    languageMode: str = "english"
    safety: dict[str, Any] = field(default_factory=dict)
    intentProfile: dict[str, Any] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    matchedItems: list[dict[str, Any]] = field(default_factory=list)
    knowledgeDocs: list[dict[str, Any]] = field(default_factory=list)
    draftOrder: dict[str, Any] = field(default_factory=dict)
    replyText: str = ""
    responseSource: str = ""
    localizationEval: dict[str, Any] = field(default_factory=dict)
    toolEvents: list[AgentToolEvent] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add_event(
        self,
        *,
        agent: str,
        tool: str,
        summary: str = "",
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        self.toolEvents.append(
            AgentToolEvent(
                agent=agent,
                tool=tool,
                status=status,
                summary=summary,
                input=input_data or {},
                output=output_data or {},
            )
        )
