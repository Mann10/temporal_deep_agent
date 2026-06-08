"""
The LLM step — the one non-deterministic primitive in the deep-agent system.

Takes the agent state, the available tool schemas, and the assembled
system prompt. Returns a serialised AIMessage dict that the workflow
appends to the message history.

`llm_step` is the single activity entry point; it dispatches to the real
LLM or the scripted mock based on the LLM_BACKEND env var.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from temporalio import activity

from ..config import LLM_BACKEND, MOCK_LLM_SCRIPT


def _reconstruct_messages(message_dicts: list[dict]) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    out = []
    for d in message_dicts:
        role = d.get("role")
        if role == "user":
            out.append(HumanMessage(content=d["content"]))
        elif role == "assistant":
            tc = d.get("tool_calls") or []
            out.append(AIMessage(content=d.get("content") or "", tool_calls=tc))
        elif role == "tool":
            out.append(ToolMessage(content=d["content"], tool_call_id=d["tool_call_id"]))
    return out


def _serialise_ai_message(response) -> dict:
    content = response.content or ""
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {"id": tc["id"], "name": tc["name"], "args": tc["args"]}
            for tc in (response.tool_calls or [])
        ],
    }


_mock_state: dict[str, dict] = {}


async def _mock_llm_step(state_dict: dict, tool_schemas: list[dict], system_prompt: str) -> dict:
    workflow_id = activity.info().workflow_id
    if workflow_id not in _mock_state:
        script = json.loads(Path(MOCK_LLM_SCRIPT).read_text(encoding="utf-8"))
        _mock_state[workflow_id] = {
            "script": script,
            "index": 0,
            "path": MOCK_LLM_SCRIPT,
        }

    state = _mock_state[workflow_id]
    steps = state["script"]["steps"]
    if state["index"] >= len(steps):
        raise RuntimeError(
            f"Mock LLM script {state['path']!r} exhausted at step {state['index']}. "
            f"Total steps: {len(steps)}."
        )

    response = steps[state["index"]]
    state["index"] += 1
    return response


async def _real_llm_step(state_dict: dict, tool_schemas: list[dict], system_prompt: str) -> dict:
    from langchain_core.messages import SystemMessage
    from ..llm import build_llm

    messages = _reconstruct_messages(state_dict["messages"])
    llm = build_llm().bind_tools(tool_schemas)
    response = await llm.ainvoke([SystemMessage(content=system_prompt), *messages])
    return _serialise_ai_message(response)


@activity.defn
async def llm_step(state_dict: dict, tool_schemas: list[dict], system_prompt: str) -> dict:
    if LLM_BACKEND == "mock":
        return await _mock_llm_step(state_dict, tool_schemas, system_prompt)
    return await _real_llm_step(state_dict, tool_schemas, system_prompt)
