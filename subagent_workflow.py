"""
SubAgentWorkflow — child workflow that runs one sub-agent.

Spawned by the parent's `task` tool via `workflow.start_child_workflow`. The
parent passes the sub-agent type and a description; this workflow looks up
the config in SUBAGENT_REGISTRY, builds a narrower tool list and a
type-specific system prompt, and runs the same LLM/tool loop as the parent.

max_depth=1 is enforced structurally: the sub-agent's tool list never
includes `task`, so the LLM never sees a way to recurse. (The dispatch
keeps a defensive `task` branch that returns a clear error if the LLM
hallucinates the name.)

No signals, no queries, no continue_as_new — sub-agents are short-lived.
If the loop exceeds MAX_TURNS the workflow returns an error string instead
of looping.

Returns: a string (the sub-agent's final answer). The parent wraps it in
a tool message and appends to its own state.
"""
from __future__ import annotations

from temporalio import workflow

from .activities.llm_step import llm_step
from .activities.tools import TOOL_REGISTRY, _run_tool, get_tool_schemas
from .config import (
    GENERIC_TOOL_TIMEOUT,
    LLM_ACTIVITY_TIMEOUT,
    MAX_TURNS,
    SA_INT,
    SA_KEYWORD,
    STANDARD_RETRY,
)
from .state import AgentState, select_messages_for_llm
from .subagents import SUBAGENT_REGISTRY, SubAgentConfig


@workflow.defn
class SubAgentWorkflow:
    def __init__(self):
        self.state: AgentState | None = None
        self.subagent_type: str | None = None

    @workflow.run
    async def run(self, subagent_type: str, description: str) -> str:
        if subagent_type not in SUBAGENT_REGISTRY:
            return (
                f"[unknown subagent_type: {subagent_type!r}. "
                f"Available: {sorted(SUBAGENT_REGISTRY)}]"
            )

        config = SUBAGENT_REGISTRY[subagent_type]
        self.subagent_type = subagent_type
        self.state = AgentState.for_subagent(description, subagent_type)
        workflow.upsert_search_attributes(_search_attrs(self.state))

        return await self._turn_loop(config)

    async def _turn_loop(self, config: SubAgentConfig) -> str:
        system_prompt = config.system_prompt_with_format_hint()
        tool_schemas = get_tool_schemas(config.tools)

        while True:
            # Token-saving: only send a bounded message window into llm_step.
            # Keep: first user/description message + last 8 messages verbatim.
            llm_state = {"messages": select_messages_for_llm(
                self.state.messages,
                include_first_user=True,
                tail_n=8,
            )}
            ai_msg = await workflow.execute_activity(
                llm_step,
                args=[llm_state, tool_schemas, system_prompt],
                start_to_close_timeout=LLM_ACTIVITY_TIMEOUT,
                retry_policy=STANDARD_RETRY,
            )
            self.state.messages.append(ai_msg)
            self.state.turn += 1
            workflow.upsert_search_attributes(_search_attrs(self.state))

            if not ai_msg.get("tool_calls"):
                return ai_msg.get("content") or ""

            for tc in ai_msg["tool_calls"]:
                tool_msg = await self._dispatch(tc)
                self.state.messages.append(tool_msg)

            if self.state.turn > MAX_TURNS:
                return (
                    f"[subagent {self.subagent_type!r} exceeded "
                    f"MAX_TURNS={MAX_TURNS} without final answer]"
                )

    async def _dispatch(self, tc: dict) -> dict:
        name = tc["name"]
        args = tc.get("args", {})
        call_id = tc["id"]

        if name not in TOOL_REGISTRY:
            return _tool_message(call_id, f"(unknown tool: {name!r})")

        entry = TOOL_REGISTRY[name]
        kind = entry["kind"]

        if kind == "in_workflow":
            if name == "write_todos":
                self.state.todos = args.get("todos", [])
                return _tool_message(call_id, "ok")
            return _tool_message(call_id, f"(unhandled in_workflow tool: {name!r})")

        if kind == "task":
            return _tool_message(
                call_id,
                "(sub-agents cannot spawn sub-agents: task is depth-limited to 1)",
            )

        if kind == "generic":
            result = await workflow.execute_activity(
                _run_tool,
                args=[name, args],
                start_to_close_timeout=GENERIC_TOOL_TIMEOUT,
                retry_policy=STANDARD_RETRY,
            )
            return _tool_message(call_id, result)

        if kind == "dedicated":
            if name == "web_search" and self.state.tavily_count >= self.state.max_tavily_calls:
                return _tool_message(
                    call_id,
                    f"(web_search cap reached: {self.state.tavily_count}/"
                    f"{self.state.max_tavily_calls}) — synthesize with what you have",
                )
            result = await workflow.execute_activity(
                entry["activity"],
                args=[args],
                start_to_close_timeout=entry["timeout"],
                retry_policy=entry["retry_policy"],
            )
            if name == "web_search":
                self.state.tavily_count += 1
            return _tool_message(call_id, result)

        return _tool_message(call_id, f"(unknown tool kind: {kind!r})")


def _tool_message(call_id: str, content: str) -> dict:
    return {"role": "tool", "content": content, "tool_call_id": call_id}


def _search_attrs(state: AgentState) -> dict:
    current_todo = ""
    for t in state.todos:
        if t.get("status") == "in_progress":
            current_todo = t.get("content", "")
            break
    return {
        SA_KEYWORD: [(
            f"agent=subagent,"
            f"depth={state.depth},"
            f"subagent={state.subagent_type or ''},"
            f"current_todo={current_todo}"
        )],
        SA_INT: [state.turn],
    }
