"""
Infusion — Claude provider.

Calls the Claude CLI directly via subprocess (not through CLITunnel.complete
to avoid circular routing when AOS_USE_INFUSION=true).
"""
from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_TIMEOUT = 120


class ClaudeProvider:
    name = "claude"

    def is_available(self) -> bool:
        return bool(shutil.which("claude"))

    def complete(self, prompt: str, system: str = "") -> str:
        claude_bin = shutil.which("claude")
        if not claude_bin:
            raise RuntimeError("claude CLI not found in PATH")
        full = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}" if system else prompt
        proc = subprocess.run(
            [claude_bin, "-p", full],
            capture_output=True, text=True, timeout=_TIMEOUT,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise RuntimeError(f"claude CLI failed (code={proc.returncode}): {proc.stderr[:200]}")
        return proc.stdout.strip()
