"""
CLI to query and signal a running deep agent workflow.

Usage:
    python signal_tool.py status <workflow-id>
    python signal_tool.py todos <workflow-id>
    python signal_tool.py messages <workflow-id>
    python signal_tool.py inject-message <workflow-id> <text>
    python signal_tool.py interrupt <workflow-id>
    python signal_tool.py cancel <workflow-id>
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv
from temporalio.client import Client

_PKG_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from temporal_deep_agent.workflow import DeepAgentWorkflow

load_dotenv()


async def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__.strip())
        sys.exit(1)

    cmd, workflow_id = sys.argv[1], sys.argv[2]

    client = await Client.connect(os.getenv("TEMPORAL_ADDRESS", "localhost:7233"))
    handle = client.get_workflow_handle(workflow_id, result_type=DeepAgentWorkflow.run)

    if cmd == "status":
        state = await handle.query("status")
        print(json.dumps(state, indent=2))

    elif cmd == "todos":
        todos = await handle.query("todos")
        print(json.dumps(todos, indent=2))

    elif cmd == "messages":
        messages = await handle.query("messages")
        print(json.dumps(messages, indent=2))

    elif cmd == "inject-message":
        if len(sys.argv) < 4:
            print("error: inject-message needs <workflow-id> <text>")
            sys.exit(1)
        text = " ".join(sys.argv[3:])
        await handle.signal("inject_message", {"role": "user", "content": text})
        print(f"injected message into {workflow_id}")

    elif cmd == "interrupt":
        await handle.signal("interrupt")
        print(f"interrupt sent to {workflow_id}")

    elif cmd == "cancel":
        await handle.signal("cancel")
        print(f"cancel sent to {workflow_id}")

    else:
        print(f"unknown command: {cmd}")
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
