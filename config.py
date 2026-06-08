"""
Shared constants. Single source of truth — import from here.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from temporalio.common import RetryPolicy
from dotenv import load_dotenv
load_dotenv()

# ── Filesystem ────────────────────────────────────────────────────────────────
FS_ROOT = Path(os.getenv("FS_ROOT", "./fs_data")).resolve()
REPORTS_DIR = FS_ROOT / "reports"

# ── Temporal ──────────────────────────────────────────────────────────────────
TASK_QUEUE = os.getenv("TASK_QUEUE", "deep-research-queue")
TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")

# ── Agent config ──────────────────────────────────────────────────────────────
MAX_DEPTH = 1
MAX_TURNS = int(os.getenv("MAX_TURNS", "100"))
LLM_BACKEND = os.getenv("LLM_BACKEND", "real")
MOCK_LLM_SCRIPT = os.getenv("MOCK_LLM_SCRIPT", "./mock_llm_scripts/example.json")
BACKEND = os.getenv("BACKEND", "local")

# Hard caps enforced by the workflow. Overridden per-run by the topic
# parser in starter.py when the user specifies e.g. "max 2 subagents".
MAX_SUBAGENTS_DEFAULT = int(os.getenv("MAX_SUBAGENTS_DEFAULT", "3"))
MAX_TAVILY_CALLS_DEFAULT = int(os.getenv("MAX_TAVILY_CALLS_DEFAULT", "10"))

# ── Timeouts ──────────────────────────────────────────────────────────────────
LLM_ACTIVITY_TIMEOUT = timedelta(minutes=2)
GENERIC_TOOL_TIMEOUT = timedelta(seconds=30)
WEB_SEARCH_TIMEOUT = timedelta(seconds=30)
SUBAGENT_TIMEOUT = timedelta(minutes=8)

# ── Retry policies ────────────────────────────────────────────────────────────
STANDARD_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)

WEB_SEARCH_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=5,
)

SUBAGENT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_attempts=2,
)

# ── Continue-as-new ───────────────────────────────────────────────────────────
CONTINUE_AS_NEW_BYTES = int(os.getenv("CONTINUE_AS_NEW_BYTES", "2000000"))
MAX_CONTINUE_AS_NEW = int(os.getenv("MAX_CONTINUE_AS_NEW", "5"))

# ── Search attributes ─────────────────────────────────────────────────────────
# Predefined Temporal slots — no registration required.
SA_KEYWORD = "CustomKeywordField"
SA_INT = "CustomIntField"

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL = os.getenv("MODEL", "openai:gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "fake")
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER")
