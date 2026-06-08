"""
Start a deep research run.

    python starter.py "US stock market crashes and updates for today"
    # or, with no args, uses a default topic:
    python starter.py

Caps can be requested in the topic string, e.g.:
    python starter.py "AI in healthcare, max 2 subagents, limit 5 web searches"
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid

# Make absolute imports (`from temporal_deep_agent.workflow import ...`)
# work both when run as `python starter.py` (script's dir on sys.path) and
# `python -m temporal_deep_agent.starter` (cwd on sys.path).
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from dotenv import load_dotenv
from temporalio.client import Client

load_dotenv()

from temporal_deep_agent.config import (
    MAX_SUBAGENTS_DEFAULT,
    MAX_TAVILY_CALLS_DEFAULT,
    TASK_QUEUE,
    TEMPORAL_ADDRESS,
)
from temporal_deep_agent.state import AgentState
from temporal_deep_agent.workflow import DeepAgentWorkflow


_SUBAGENT_CAP_RE = re.compile(
    r"(?:max(?:imum)?|limit(?:ed)?\s*to|up\s*to|no\s*more\s*than|spawn|use)\s*"
    r"(\d+)\s*subagents?",
    re.IGNORECASE,
)

_TAVILY_CAP_RE = re.compile(
    r"(?:max(?:imum)?|limit(?:ed)?\s*to|up\s*to|no\s*more\s*than)?\s*"
    r"(\d+)\s*(?:web\s*search(?:es)?|tavily\s*calls?|searches)",
    re.IGNORECASE,
)


def _parse_topic_limits(topic: str) -> tuple[int, int]:
    """Extract (max_subagents, max_tavily_calls) from a topic string.

    Returns the configured defaults if no caps are mentioned.
    """
    max_sub = MAX_SUBAGENTS_DEFAULT
    max_tav = MAX_TAVILY_CALLS_DEFAULT

    if m := _SUBAGENT_CAP_RE.search(topic):
        max_sub = int(m.group(1))
    if m := _TAVILY_CAP_RE.search(topic):
        max_tav = int(m.group(1))

    return max_sub, max_tav


async def main(topic: str) -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)

    max_sub, max_tav = _parse_topic_limits(topic)

    slug = "".join(c for c in topic[:40].lower() if c.isalnum() or c == "-") or "run"
    workflow_id = f"research-{slug}-{uuid.uuid4().hex[:8]}"

    state_dict = AgentState.initial(
        topic, max_subagents=max_sub, max_tavily_calls=max_tav
    ).to_dict()

    print(f"Topic      : {topic}")
    print(f"Workflow ID: {workflow_id}")
    print(f"Subagents  : cap={max_sub}    Tavily: cap={max_tav}\n")

    handle = await client.start_workflow(
        DeepAgentWorkflow.run,
        state_dict,
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    print("Waiting for workflow to finish (Ctrl-C to detach; workflow continues server-side)...")
    result = await handle.result()

    print(f"\nStatus: {result['status']}")
    answer = result.get("answer")
    if answer:
        print(f"\n=== Answer ===\n{answer}")


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) or "agentic AI in healthcare 2026"
    asyncio.run(main(topic))
