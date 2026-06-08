"""
Backend protocol and LocalFSBackend implementation.

The Backend is the file-system abstraction the LLM's tools operate on. It
lives in-process (the activity calls it directly); it does NOT go through
Temporal. Files are stored on whichever worker picks the activity.

v1 ships only `LocalFSBackend` (single-worker MVP). The protocol is here so
that `S3Backend` (v1.5) can be plugged in via the BACKEND env var without
touching the activity code.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .config import BACKEND, FS_ROOT


class Backend(Protocol):
    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> str: ...
    async def edit(self, path: str, old: str, new: str) -> str: ...
    async def ls(self, path: str = ".") -> str: ...
    async def glob_(self, pattern: str) -> str: ...
    async def grep(self, pattern: str, path: str = ".") -> str: ...


class LocalFSBackend:
    """Single-worker filesystem backend rooted at FS_ROOT.

    With multiple workers, files written by one worker may not be visible
    to another. Acceptable for the v1 single-worker MVP.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe_path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root)):
            raise ValueError(f"Path {rel!r} escapes FS_ROOT")
        return p

    async def read(self, path: str) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"(not found: {path})"
        return p.read_text(encoding="utf-8")

    async def write(self, path: str, content: str) -> str:
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def edit(self, path: str, old: str, new: str) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"(not found: {path})"
        content = p.read_text(encoding="utf-8")
        if old not in content:
            return f"(string not found in {path})"
        p.write_text(content.replace(old, new, 1), encoding="utf-8")
        return f"Edited {path}"

    async def ls(self, path: str = ".") -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"(not found: {path})"
        if p.is_file():
            return path
        return "\n".join(sorted(str(c.relative_to(self.root)) for c in p.iterdir()))

    async def glob_(self, pattern: str) -> str:
        matches = sorted(
            str(p.relative_to(self.root)) for p in self.root.glob(pattern)
        )
        return "\n".join(matches) if matches else "(no matches)"

    async def grep(self, pattern: str, path: str = ".") -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"(not found: {path})"
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        hits = []
        for f in files:
            try:
                for i, line in enumerate(
                    f.read_text(encoding="utf-8").splitlines(), 1
                ):
                    if pattern in line:
                        hits.append(
                            f"{f.relative_to(self.root)}:{i}:{line}"
                        )
            except UnicodeDecodeError:
                continue
        return "\n".join(hits) if hits else "(no matches)"


def get_backend() -> Backend:
    if BACKEND == "local":
        return LocalFSBackend(FS_ROOT)
    raise NotImplementedError(f"BACKEND={BACKEND!r} not implemented in v1")
