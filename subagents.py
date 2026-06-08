"""
Sub-agent registry. Mirrors deepagents' SubAgentMiddleware contract: a parent
LLM picks a sub-agent by name (via the `task` tool), and the dispatcher
launches it as a child workflow with the configured system prompt and tool
list.

The `tools` field is a list of TOOL_REGISTRY names. The workflow code
filters the actual tool schemas by this list when starting the child.

max_depth=1 is enforced structurally: SubAgentWorkflow's tool list never
includes `task`, so the subagent cannot recurse even if it wanted to.
"""
from __future__ import annotations

from dataclasses import dataclass

from .activities.tools import ALL_TOOL_NAMES
from .prompts import REPORT_WRITER_PROMPT, RESEARCHER_PROMPT


@dataclass
class SubAgentConfig:
    """Static config for a registered sub-agent type."""
    name: str
    description: str
    system_prompt: str
    tools: list[str]
    model: str | None = None
    expected_output_format: str = "Plain text. Be concise."

    def system_prompt_with_format_hint(self) -> str:
        return (
            f"{self.system_prompt}\n\n"
            f"## Expected output format\n{self.expected_output_format}"
        )


SUBAGENT_REGISTRY: dict[str, SubAgentConfig] = {
    "researcher": SubAgentConfig(
        name="researcher",
        description=(
            "Web research specialist. Use to gather facts on a focused "
            "question via web search and file reads. Has its own context "
            "window, so it's good for bundled multi-angle research that "
            "would bloat the parent thread."
        ),
        system_prompt=RESEARCHER_PROMPT,
        tools=["web_search", "read_file", "write_file", "ls", "write_todos"],
        model=None,
        expected_output_format=(
            "Bullet list of facts with dates and figures. Under 300 words. "
            "Do not write a full report."
        ),
    ),
    "report-writer": SubAgentConfig(
        name="report-writer",
        description=(
            "Report-writer specialist. Takes a research summary and writes "
            "a properly formatted markdown report to `reports/{slug}.md` "
            "with all required fields (TITLE, DATE, Executive Summary, "
            "Key Findings, Analysis, Conclusion, Sources). Returns only a "
            "brief confirmation — keeps the parent's context clean."
        ),
        system_prompt=REPORT_WRITER_PROMPT,
        tools=["read_file", "write_file", "ls"],
        model=None,
        expected_output_format=(
            "A single short line: 'Wrote <N>-word report to <path>'. "
            "Do not return the full report content."
        ),
    ),
}


def get_subagent(name: str) -> SubAgentConfig:
    if name not in SUBAGENT_REGISTRY:
        raise KeyError(
            f"Unknown subagent_type: {name!r}. "
            f"Available: {sorted(SUBAGENT_REGISTRY)}"
        )
    return SUBAGENT_REGISTRY[name]


def task_tool_subagent_listing() -> str:
    """Formatted list of available sub-agents for the `task` tool description."""
    return "\n".join(
        f"- {cfg.name}: {cfg.description}" for cfg in SUBAGENT_REGISTRY.values()
    )
