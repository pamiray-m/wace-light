"""
CLI Tunnel — routes LLM traffic through the local Claude CLI subprocess.

Eliminates direct Anthropic API calls (paid credits) by using the Claude
Code OAuth session via `claude -p`.

Two surfaces:
  complete(prompt, system)                     — simple text completion
  complete_with_tools(messages, tools, system) — one-round Anthropic-format response
    Returns {"stop_reason": "tool_use"|"end_turn", "content": [...]}
    matching the shape _run_model_loop() already expects in JarvisService.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

_TIMEOUT = 120  # seconds per CLI call
_TOOL_CALL_RE = re.compile(r"<TOOL_CALL>(.*?)</TOOL_CALL>", re.DOTALL)


class CLIUnavailableError(RuntimeError):
    """Raised when the claude CLI is not in PATH or returns a non-zero exit."""


def _bridge_env() -> dict:
    """Subprocess env that forces `claude` onto the OAuth subscription.

    The whole point of the bridge is to bypass the *uncredited Anthropic API*.
    If ANTHROPIC_API_KEY is left in the env, the Claude Code CLI uses it (and
    hits the same "credit balance too low" error). We strip it so the CLI falls
    back to CLAUDE_CODE_OAUTH_TOKEN / the stored OAuth session (the Pro/Max
    subscription), which is not metered on API credits.
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def _run_cli(prompt: str) -> str:
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise CLIUnavailableError(
            "claude CLI not found in PATH. "
            "Install Claude Code or set AOS_LLM_BACKEND=api to use the Anthropic API."
        )
    proc = subprocess.run(
        [claude_bin, "-p", prompt],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT,
        env=_bridge_env(),
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise CLIUnavailableError(
            f"claude CLI exited with code {proc.returncode}: {proc.stderr[:300]}"
        )
    return proc.stdout.strip()


def _format_tools(tools: list[dict]) -> str:
    lines: list[str] = []
    for t in tools:
        name = t.get("name", "")
        desc = t.get("description", "")
        schema = t.get("input_schema", {})
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        lines.append(f"Tool: {name}")
        lines.append(f"  {desc}")
        for pname, pdef in props.items():
            req = " [required]" if pname in required else ""
            lines.append(
                f"  - {pname} ({pdef.get('type', 'any')}){req}: {pdef.get('description', '')}"
            )
        lines.append("")
    return "\n".join(lines)


def _format_messages(messages: list[dict]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "").upper()
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]\n{content}")
        elif isinstance(content, list):
            texts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "text":
                    texts.append(block.get("text", ""))
                elif btype == "tool_use":
                    texts.append(
                        f"[called {block.get('name')} with "
                        f"{json.dumps(block.get('input', {}))}]"
                    )
                elif btype == "tool_result":
                    texts.append(f"[tool result: {block.get('content', '')}]")
            parts.append(f"[{role}]\n" + "\n".join(texts))
    return "\n\n".join(parts)


class CLITunnel:
    """
    Intercepts LLM calls and routes them through `claude -p` instead of the
    Anthropic API, consuming the Claude Code OAuth session rather than paid
    API credits.
    """

    def complete(self, prompt: str, system: str = "") -> str:
        """Simple text completion — routes through Infusion if AOS_USE_INFUSION=true."""
        import os
        if os.environ.get("AOS_USE_INFUSION", "").lower() == "true":
            from src.infusion.engine import infusion_engine
            return infusion_engine.complete(prompt, system)
        full = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}" if system else prompt
        return _run_cli(full)

    def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> dict:
        """
        One round of inference with optional tool use.

        Formats conversation history and tool schemas into a single CLI prompt.
        Detects tool-call intent via a <TOOL_CALL> XML marker in the response.

        Returns an Anthropic-format response dict consumed by _run_model_loop:
          tool requested → {"stop_reason": "tool_use",  "content": [tool_use block]}
          final answer   → {"stop_reason": "end_turn",  "content": [text block]}
        """
        tool_section = ""
        if tools:
            tool_section = (
                "\n\n## AVAILABLE TOOLS\n"
                + _format_tools(tools)
                + "\n## TOOL CALL PROTOCOL\n"
                "To call a tool output ONLY a TOOL_CALL block (nothing else on the line):\n"
                '<TOOL_CALL>{"name": "<tool_name>", "input": {<args as JSON>}}</TOOL_CALL>\n'
                "To give your final answer respond in plain text (no TOOL_CALL block).\n"
            )

        if system:
            sys_block = f"[SYSTEM]\n{system}{tool_section}"
        else:
            sys_block = f"[SYSTEM]{tool_section}"

        history = _format_messages(messages)
        prompt = f"{sys_block}\n\n[CONVERSATION]\n{history}\n\n[ASSISTANT RESPONSE]"

        try:
            raw = _run_cli(prompt)
        except CLIUnavailableError as exc:
            logger.error("[CLITunnel] CLI call failed: %s", exc)
            return {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": f"CLI unavailable: {exc}"}],
            }

        match = _TOOL_CALL_RE.search(raw)
        if match:
            try:
                payload = json.loads(match.group(1).strip())
                return {
                    "stop_reason": "tool_use",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": f"cli_{uuid.uuid4().hex[:12]}",
                            "name": payload.get("name", ""),
                            "input": payload.get("input", {}),
                        }
                    ],
                }
            except (json.JSONDecodeError, ValueError):
                logger.warning("[CLITunnel] TOOL_CALL block contained invalid JSON; treating as text")

        return {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": raw}],
        }


# Process-level singleton — stateless, safe to share.
cli_tunnel = CLITunnel()
