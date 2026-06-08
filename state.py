"""
AgentState — the deterministic state held by DeepAgentWorkflow and SubAgentWorkflow.

Lives in the workflow. Crosses Temporal activity boundaries as a plain dict.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


def select_messages_for_llm(
    messages: list[dict],
    *,
    include_first_user: bool = True,
    tail_n: int = 10,
) -> list[dict]:
    """
    Token-saving message selection without summarization.

    Keeps (optionally) the first user/topic message plus the last `tail_n`
    messages verbatim. This preserves recent tool results needed for the
    next reasoning step while bounding context growth.
    """
    if not messages:
        return []

    first_idx: int | None = None
    if include_first_user:
        for i, m in enumerate(messages):
            if m.get("role") == "user":
                first_idx = i
                break

    if first_idx is None:
        # No user message found; just take a verbatim tail.
        return messages[-tail_n:] if tail_n > 0 else []

    tail = messages[-tail_n:] if tail_n > 0 else []
    selected = [messages[first_idx], *tail]

    # De-duplicate while preserving order (object identity is fine here
    # because we're selecting from the same list instance).
    out: list[dict] = []
    seen: set[int] = set()
    for m in selected:
        key = id(m)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


@dataclass
class AgentState:
    """Mutable state held by a deep-agent workflow.

    Replayed from event history on resume. Survives `continue_as_new` via
    `to_dict` / `from_dict`.
    """
    messages: list[dict] = field(default_factory=list)
    todos: list[dict] = field(default_factory=list)
    turn: int = 0
    depth: int = 0
    subagent_type: str | None = None
    injected_messages: list[dict] = field(default_factory=list)
    topic: str = ""
    continue_as_new_count: int = 0

    # Hard caps + live counters for tool invocation limits. Enforced in
    # the workflow's _dispatch paths. Counters only increment on
    # successful dispatches; cap-hit attempts return an error tool
    # message but don't count.
    max_subagents: int = 3
    max_tavily_calls: int = 10
    subagent_count: int = 0
    tavily_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentState":
        return cls(**d)

    @classmethod
    def initial(cls, topic: str, max_subagents: int = 3, max_tavily_calls: int = 10) -> "AgentState":
        return cls(
            messages=[{"role": "user", "content": topic}],
            topic=topic,
            max_subagents=max_subagents,
            max_tavily_calls=max_tavily_calls,
        )

    @classmethod
    def for_subagent(cls, description: str, subagent_type: str, max_tavily_calls: int = 10) -> "AgentState":
        return cls(
            messages=[{"role": "user", "content": description}],
            depth=1,
            subagent_type=subagent_type,
            topic=description,
            max_tavily_calls=max_tavily_calls,
        )
