"""
Tool registry and tool-related activities.

TOOL_REGISTRY is the central manifest. Each tool has a `kind`:
- "in_workflow": handled in workflow code, no activity (write_todos)
- "task": spawns a child workflow (task)
- "generic": dispatched via _run_tool activity (filesystem tools)
- "dedicated": each tool is its own activity (web_search)

ALL_TOOL_NAMES is computed from the registry. Sub-agent configs (in
subagents.py) reference tool names from this list.
"""
from __future__ import annotations

import os

from temporalio import activity

from ..backend import get_backend
from ..config import WEB_SEARCH_RETRY, WEB_SEARCH_TIMEOUT


@activity.defn
async def _run_tool(name: str, args: dict) -> str:
    backend = get_backend()
    if name == "read_file":
        return await backend.read(args["path"])
    if name == "write_file":
        return await backend.write(args["path"], args["content"])
    if name == "edit_file":
        return await backend.edit(args["path"], args["old"], args["new"])
    if name == "ls":
        return await backend.ls(args.get("path", "."))
    if name == "glob":
        return await backend.glob_(args["pattern"])
    if name == "grep":
        return await backend.grep(args["pattern"], args.get("path", "."))
    raise ValueError(f"Unknown generic tool: {name!r}")


@activity.defn
async def web_search(args: dict) -> str:
    from tavily import TavilyClient
    query = args.get("query", "")
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", ""))
    results = client.search(query, max_results=5).get("results", [])
    if not results:
        return "No results found."
    return "\n---\n".join(r["content"] for r in results if r.get("content"))


WRITE_TODOS_SCHEMA = {
    "name": "write_todos",
    "description": (
        "Update the todo list. Use this to plan and track progress on a "
        "multi-step task. Re-plan when the situation changes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "done"],
                        },
                        "content": {"type": "string"},
                    },
                    "required": ["status", "content"],
                },
            },
        },
        "required": ["todos"],
    },
}

TASK_SCHEMA = {
    "name": "task",
    "description": (
        "Delegate a task to a sub-agent. The sub-agent runs in an isolated "
        "context and returns a single string result. See the system prompt "
        "for available sub-agent types."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subagent_type": {
                "type": "string",
                "description": "The type of sub-agent (e.g., 'researcher').",
            },
            "description": {
                "type": "string",
                "description": "Detailed task description for the sub-agent.",
            },
        },
        "required": ["subagent_type", "description"],
    },
}

READ_FILE_SCHEMA = {
    "name": "read_file",
    "description": "Read a file from the project filesystem.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the project root.",
            },
        },
        "required": ["path"],
    },
}

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": "Write content to a file. Creates parent directories as needed.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
}

EDIT_FILE_SCHEMA = {
    "name": "edit_file",
    "description": "Replace a string in a file. The `old` string must appear exactly once.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
        },
        "required": ["path", "old", "new"],
    },
}

LS_SCHEMA = {
    "name": "ls",
    "description": "List files in a directory. Default is the project root.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": "."},
        },
    },
}

GLOB_SCHEMA = {
    "name": "glob",
    "description": "Find files matching a glob pattern (relative to project root). Use '**' for recursive.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
        },
        "required": ["pattern"],
    },
}

GREP_SCHEMA = {
    "name": "grep",
    "description": "Search for a substring in files under a directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "default": "."},
        },
        "required": ["pattern"],
    },
}

WEB_SEARCH_SCHEMA = {
    "name": "web_search",
    "description": "Search the web. Returns up to 5 result snippets.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
    },
}


TOOL_REGISTRY: dict[str, dict] = {
    "write_todos": {"kind": "in_workflow", "schema": WRITE_TODOS_SCHEMA},
    "task": {"kind": "task", "schema": TASK_SCHEMA},
    "read_file": {"kind": "generic", "schema": READ_FILE_SCHEMA},
    "write_file": {"kind": "generic", "schema": WRITE_FILE_SCHEMA},
    "edit_file": {"kind": "generic", "schema": EDIT_FILE_SCHEMA},
    "ls": {"kind": "generic", "schema": LS_SCHEMA},
    "glob": {"kind": "generic", "schema": GLOB_SCHEMA},
    "grep": {"kind": "generic", "schema": GREP_SCHEMA},
    "web_search": {
        "kind": "dedicated",
        "schema": WEB_SEARCH_SCHEMA,
        "activity": web_search,
        "timeout": WEB_SEARCH_TIMEOUT,
        "retry_policy": WEB_SEARCH_RETRY,
    },
}

ALL_TOOL_NAMES: list[str] = list(TOOL_REGISTRY.keys())


def get_tool_schemas(tool_names: list[str]) -> list[dict]:
    return [TOOL_REGISTRY[name]["schema"] for name in tool_names]
