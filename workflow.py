"""
DeepAgentWorkflow — the parent orchestrator.

State lives on `self.state` (an AgentState, deterministic). All non-deterministic
work happens in activities (LLM calls, tool calls, child workflows).

The turn loop:
  1. Drain injected_messages
  2. Check cancel / interrupt flags
  3. Build system prompt + tool schemas (parent's full set)
  4. Call llm_step activity
  5. If no tool_calls -> return final answer
  6. Dispatch each tool call (in_workflow / task / generic / dedicated)
  7. Upsert search attributes
  8. Check continue-as-new
  9. Loop
"""
from __future__ import annotations

from temporalio import workflow

from .activities.llm_step import llm_step
from .activities.tools import ALL_TOOL_NAMES, TOOL_REGISTRY, _run_tool, get_tool_schemas
from .config import (
    CONTINUE_AS_NEW_BYTES,
    GENERIC_TOOL_TIMEOUT,
    LLM_ACTIVITY_TIMEOUT,
    MAX_CONTINUE_AS_NEW,
    MAX_TURNS,
    SA_INT,
    SA_KEYWORD,
    STANDARD_RETRY,
    SUBAGENT_RETRY,
    SUBAGENT_TIMEOUT,
)
from .prompts import build_parent_system_prompt
from .state import AgentState, select_messages_for_llm
from .subagents import SUBAGENT_REGISTRY, task_tool_subagent_listing


@workflow.defn
class DeepAgentWorkflow:
    def __init__(self):
        self.state: AgentState | None = None
        self._interrupt_requested = False
        self._cancelled = False

    @workflow.query
    def status(self) -> dict:
        return {
            "workflow_id": workflow.info().workflow_id,
            "run_id": workflow.info().run_id,
            "turn": self.state.turn if self.state else 0,
            "current_todo": _current_todo_str(self.state),
        }

    @workflow.query
    def todos(self) -> list[dict]:
        return self.state.todos if self.state else []

    @workflow.query
    def messages(self) -> list[dict]:
        return self.state.messages if self.state else []

    @workflow.signal
    def inject_message(self, msg: dict):
        if self.state is not None:
            self.state.injected_messages.append(msg)

    @workflow.signal
    def interrupt(self):
        self._interrupt_requested = True

    @workflow.signal
    def cancel(self):
        self._cancelled = True

    @workflow.run
    async def run(self, state_dict: dict) -> dict:
        self.state = AgentState.from_dict(state_dict)
        workflow.upsert_search_attributes(_search_attrs(self.state))
        return await self._turn_loop()

    async def _turn_loop(self) -> dict:
        while True:
            while self.state.injected_messages:
                self.state.messages.append(self.state.injected_messages.pop(0))

            if self._cancelled:
                return {"status": "cancelled", "answer": None,
                        "state": self.state.to_dict()}

            if self._interrupt_requested:
                return {"status": "interrupted", "answer": None,
                        "state": self.state.to_dict()}

            system_prompt = build_parent_system_prompt(
                available_agents=task_tool_subagent_listing(),
                budget_str=(
                    f"Subagents: {self.state.subagent_count}/{self.state.max_subagents} used. "
                    f"Tavily: {self.state.tavily_count}/{self.state.max_tavily_calls} used."
                ),
            )
            tool_schemas = get_tool_schemas(ALL_TOOL_NAMES)

            # Token-saving: only send a bounded message window into llm_step.
            # Keep: first user/topic message + last 10 messages verbatim.
            llm_state = {"messages": select_messages_for_llm(
                self.state.messages,
                include_first_user=True,
                tail_n=10,
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
                return {"status": "done", "answer": ai_msg.get("content"),
                        "state": self.state.to_dict()}

            for tc_index, tc in enumerate(ai_msg["tool_calls"]):
                tool_msg = await self._dispatch(tc, tc_index)
                self.state.messages.append(tool_msg)

            if (workflow.info().get_current_history_size() > CONTINUE_AS_NEW_BYTES
                    or self.state.turn > MAX_TURNS):
                if self.state.continue_as_new_count >= MAX_CONTINUE_AS_NEW:
                    return {"status": "max_continue_as_new", "answer": None,
                            "state": self.state.to_dict()}
                self.state.continue_as_new_count += 1
                workflow.continue_as_new(self.state.to_dict())
                return

    async def _dispatch(self, tc: dict, tc_index: int) -> dict:
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
            return await self._dispatch_task(tc, tc_index)

        if kind == "generic":
            result = await workflow.execute_activity(
                _run_tool,
                args=[name, args],
                start_to_close_timeout=GENERIC_TOOL_TIMEOUT,
                retry_policy=STANDARD_RETRY,
            )
            return _tool_message(call_id, result)

        if kind == "dedicated":
            if name == "web_search":
                # Token-cost guard for Route A:
                # If the parent has started a multi-step todo plan (Route A),
                # web_search before delegating wastes calls because the
                # researcher subagent will perform the bundled searches.
                if self.state.todos:
                    # Heuristic: if any todo is still pending/in_progress,
                    # the parent is in a delegation plan phase.
                    if any(t.get("status") in ("pending", "in_progress") for t in self.state.todos):
                        return _tool_message(
                            call_id,
                            "(web_search blocked during Route A todo planning) — "
                            "delegate the multi-angle research to the researcher subagent first.",
                        )

                if self.state.tavily_count >= self.state.max_tavily_calls:
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

        return _tool_message(call_id, f"(unknown tool kind: {kind!r})")

    async def _dispatch_task(self, tc: dict, tc_index: int) -> dict:
        from .subagent_workflow import SubAgentWorkflow

        args = tc.get("args", {})
        call_id = tc["id"]
        subagent_type = args.get("subagent_type")
        description = args.get("description", "")

        if subagent_type not in SUBAGENT_REGISTRY:
            return _tool_message(
                call_id,
                f"(unknown subagent_type: {subagent_type!r}. "
                f"Available: {sorted(SUBAGENT_REGISTRY)})",
            )

        if self.state.subagent_count >= self.state.max_subagents:
            return _tool_message(
                call_id,
                f"(subagent cap reached: {self.state.subagent_count}/"
                f"{self.state.max_subagents}) — synthesize with what you have",
            )

        # Deterministic child workflow ID: parent run_id + turn + tool_call index.
        # Avoids non-determinism errors on replay (uuid4 would generate a new value
        # each time, breaking the comparison with the recorded event).
        child_id = (
            f"{workflow.info().workflow_id}-subagent-"
            f"{workflow.info().run_id}-t{self.state.turn}-i{tc_index}"
        )

        handle = await workflow.start_child_workflow(
            SubAgentWorkflow.run,
            args=[subagent_type, description],
            id=child_id,
            execution_timeout=SUBAGENT_TIMEOUT,
            retry_policy=SUBAGENT_RETRY,
        )
        result = await handle
        self.state.subagent_count += 1
        return _tool_message(call_id, result)


def _tool_message(call_id: str, content: str) -> dict:
    return {"role": "tool", "content": content, "tool_call_id": call_id}


def _current_todo_str(state: AgentState | None) -> str:
    if state is None:
        return ""
    for t in state.todos:
        if t.get("status") == "in_progress":
            return t.get("content", "")
    return ""


def _search_attrs(state: AgentState) -> dict:
    return {
        SA_KEYWORD: [(
            f"agent=deep-research,"
            f"depth={state.depth},"
            f"subagent={state.subagent_type or ''},"
            f"current_todo={_current_todo_str(state)}"
        )],
        SA_INT: [state.turn],
    }
