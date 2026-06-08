"""
Worker entry point. Run this before starter.py.

    python worker.py
    # or
    python -m temporal_deep_agent.worker

Registers both workflows and all activities on TASK_QUEUE. Uses
UnsandboxedWorkflowRunner so workflows can do top-level local imports
(required by subagent_workflow.py, which is imported lazily by the
parent's _dispatch_task — sandboxing breaks that pattern).
"""
from __future__ import annotations

import asyncio
import os
import sys

# Make absolute imports (`from temporal_deep_agent.workflow import ...`)
# work both when run as `python worker.py` (script's dir on sys.path) and
# `python -m temporal_deep_agent.worker` (cwd on sys.path).
_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

load_dotenv()

from temporal_deep_agent.activities.llm_step import llm_step
from temporal_deep_agent.activities.tools import _run_tool, web_search
from temporal_deep_agent.config import TASK_QUEUE, TEMPORAL_ADDRESS
from temporal_deep_agent.subagent_workflow import SubAgentWorkflow
from temporal_deep_agent.workflow import DeepAgentWorkflow


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DeepAgentWorkflow, SubAgentWorkflow],
        activities=[llm_step, _run_tool, web_search],
        workflow_runner=UnsandboxedWorkflowRunner(),
        max_concurrent_activities=10,
        max_concurrent_workflow_tasks=10,
    )

    print(f"Worker listening on queue: {TASK_QUEUE!r} (address: {TEMPORAL_ADDRESS})")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
