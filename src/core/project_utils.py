"""Shared project-type detection utilities."""

from __future__ import annotations

_JS_EXTS = (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")


def detect_project_type(files_changed: list[str]) -> str:
    """Returns 'python', 'javascript', or 'mixed' based on file extensions."""
    has_py = any(f.endswith(".py") for f in files_changed)
    has_js = any(f.endswith(_JS_EXTS) for f in files_changed)
    if has_py and has_js:
        return "mixed"
    if has_js:
        return "javascript"
    return "python"
