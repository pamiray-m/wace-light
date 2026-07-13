"""
LLM Gateway — centralized Claude invocation for all of AOS.

Single point of entry for every real LLM call in the system. Used by:
  - AgentRuntimeService._execute_with_llm()  (GENERAL_REASONING, CREATIVE_ANALYSIS)
  - ClaudeAdapter.send_prompt()              (real agent instruction execution)
  - Any future module that needs Claude

Resolution order
----------------
1. ANTHROPIC_API_KEY env var → anthropic SDK (preferred)
2. ANTHROPIC_API_KEY env var → httpx direct call (fallback if SDK not installed)
3. `claude` CLI in PATH     → subprocess -p flag (uses Claude Code OAuth session)
4. Raises LLMUnavailableError

The module exposes a process-level singleton `llm_gateway` so callers don't
construct an instance each time. The singleton is stateless — safe to share.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Default model used across AOS. Override per-call for specialised tasks.
_DEFAULT_MODEL = "claude-sonnet-4-6"
_DEFAULT_MAX_TOKENS = 1024


# ---------------------------------------------------------------------------
# Uncredited-API detection + cooldown
#
# When the Anthropic API rejects calls because the account is out of credits
# (HTTP 400 "Your credit balance is too low"), or is rate/quota limited (402 /
# 429), we mark the API "uncredited" for a cooldown window and route every call
# through the local Claude CLI bridge instead (Claude Code OAuth session — no
# paid credits). This avoids paying latency on a known-dead API on every call.
#
# Cross-worker state: uvicorn runs multiple worker PROCESSES inside one
# container, so an in-memory flag would be per-worker (one worker tripping the
# cooldown wouldn't stop the others, and /health would report whichever worker
# served the request). The cooldown deadline is therefore persisted to a shared
# file (wall-clock unix timestamp) that every worker on the node reads/writes,
# so the uncredited state — and the /health signal — is one consistent truth.
# The file lives on the container's ephemeral filesystem, so a container
# restart clears it and the live API is retried (in case credits were topped up).
# ---------------------------------------------------------------------------

_CREDIT_QUOTA_MARKERS = (
    "credit balance is too low",
    "insufficient credit",
    "insufficient_quota",
    "billing",
    "quota",
    "payment required",
    "purchase credits",
    "plans & billing",
)


def _looks_like_credit_or_quota(message: str) -> bool:
    m = (message or "").lower()
    return any(marker in m for marker in _CREDIT_QUOTA_MARKERS)


def _cooldown_seconds() -> float:
    try:
        minutes = float(os.environ.get("AOS_LLM_API_COOLDOWN_MINUTES", "15"))
    except (TypeError, ValueError):
        minutes = 15.0
    return max(0.0, minutes) * 60.0


def _cooldown_file() -> str:
    """Path to the shared cross-worker cooldown file (override for tests)."""
    return (os.environ.get("AOS_LLM_COOLDOWN_FILE", "").strip()
            or os.path.join(tempfile.gettempdir(), "aos_llm_api_cooldown"))


def _read_deadline() -> float:
    """Read the shared cooldown deadline (unix ts). 0.0 if absent/corrupt."""
    try:
        with open(_cooldown_file(), "r") as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def _mark_api_uncredited(reason: str = "") -> None:
    """Flag the paid API unavailable for a cooldown window, shared across all
    workers on this node. Atomic write so concurrent workers never read a
    partial value."""
    deadline = time.time() + _cooldown_seconds()
    path = _cooldown_file()
    try:
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            f.write(repr(deadline))
        os.replace(tmp, path)   # atomic on POSIX
    except Exception as exc:  # pragma: no cover — never break the LLM call
        logger.debug("LLM gateway: could not persist cooldown: %s", exc)
    logger.warning(
        "LLM gateway: Anthropic API unavailable (credit/quota) — routing to the "
        "local Claude CLI bridge for ~%.0f min. reason=%s",
        _cooldown_seconds() / 60.0, (reason or "")[:200],
    )


def _api_in_cooldown() -> bool:
    return time.time() < _read_deadline()


def api_cooldown_remaining_seconds() -> float:
    """Seconds remaining in the uncredited-API cooldown (0 if the API is live).

    Reads the shared file so every worker reports the SAME value — exposed so
    /health and the cockpit can surface 'LLM degraded: serving via local Claude
    bridge' as one consistent signal instead of per-worker noise."""
    return max(0.0, _read_deadline() - time.time())


def reset_api_cooldown() -> None:
    """Ops/test hook — clear the uncredited cooldown so the API is retried."""
    try:
        os.remove(_cooldown_file())
    except FileNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover
        logger.debug("LLM gateway: could not clear cooldown file: %s", exc)


# W6.3 — prompt-cache opt-in counter. Created at module import time; never
# duplicated across test reloads because LabeledCounter is registered once
# in the prom singleton registry.
try:
    from src.core.observability.prom import LabeledCounter as _LabeledCounter
    cache_hints_total = _LabeledCounter(
        "aos_llm_cache_hints_total",
        "Times the gateway opted into Anthropic prompt cache for a call (by model).",
    )
except Exception:  # pragma: no cover — observability import shouldn't break the gateway
    cache_hints_total = None  # type: ignore[assignment]


def _record_cache_hint(model: str) -> None:
    """Best-effort cache-hint counter emission; never raises."""
    try:
        if cache_hints_total is not None:
            cache_hints_total.inc(labels={"model": model})
    except Exception:  # pragma: no cover
        pass


class LLMUnavailableError(RuntimeError):
    """Raised when no LLM endpoint is reachable."""


@dataclass(frozen=True)
class LLMResponse:
    """Structured response from the LLM gateway."""

    text: str
    model: str
    via: str                        # "anthropic_sdk" | "httpx" | "claude_cli"
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: dict = field(default_factory=dict)

    def parse_json(self) -> dict:
        """
        Extract the first JSON object from the response text.
        Returns an empty dict if no valid JSON is found.
        """
        match = re.search(r'\{.*\}', self.text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        return {}


class LLMGateway:
    """
    Centralized gateway for Claude invocations across AOS.

    All methods are synchronous (blocking). For async contexts use
    asyncio.to_thread() to avoid blocking the event loop.

    SAIb integration
    ----------------
    Every complete() call passes through the SAIb guard before reaching
    the LLM. The guard scans for PII, financial data, credentials, and
    classified keywords, then applies masking or blocks the call according
    to AOS_SAIB_MODE (OFF / DETECT / MASK / STRICT). The LLM response is
    unmasked before being returned, so callers always receive original values.

    To skip SAIb for a specific call (e.g., inside tests) set:
        AOS_SAIB_MODE=OFF

    Parameters
    ----------
    default_model     : Claude model ID used when no model is specified per-call.
    default_max_tokens: Token budget for each completion.
    """

    def __init__(
        self,
        default_model: str = _DEFAULT_MODEL,
        default_max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self._model = default_model
        self._max_tokens = default_max_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        system: str = "",
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        task_hint: Optional[str] = None,
        risk_hint: Optional[str] = None,
        customer_id: Optional[str] = None,
        cacheable_system: bool = False,
        mission_id: Optional[str] = None,
        api_key_override: Optional[str] = None,
        allow_bridge_fallback: bool = True,
    ) -> LLMResponse:
        """
        Send a prompt to Claude and return a structured response.

        The prompt and system are passed through SAIb before being sent.
        The response is unmasked before being returned.

        Parameters
        ----------
        prompt    : User-facing message.
        system    : System prompt (agent doctrine, role instructions, etc.).
        model     : Override the default model. When provided, the W6.1
                    router is bypassed entirely — the caller is responsible
                    for cost-vs-quality trade-off.
        max_tokens: Override the default token budget.
        task_hint : Optional hint consumed by the W6.1 router to pick a
                    cheaper model for known low-risk tasks. Ignored when
                    `model=` is provided.
        risk_hint : "high" forces Opus via the router; "low" is informational.
                    Ignored when `model=` is provided.

        Raises
        ------
        LLMUnavailableError
            When no Claude endpoint is reachable (no API key, no CLI).
        SAIbBlockedError
            When SAIb blocks the prompt due to data classification policy.
        """
        from src.saib.guard import SAIbBlockedError, saib_guard

        # --- W6.2 budget pre-check ---
        # When customer_id is provided, verify they're not already EXHAUSTED.
        # The check happens BEFORE SAIb so we don't pay SAIb scan time for a
        # call that will be rejected anyway. Raises LLMBudgetExceededError.
        if customer_id is not None:
            from src.llm.budget import budget_tracker
            budget_tracker.check_or_raise(customer_id)

        # --- LLM call wall-clock starts here so SAIb time counts toward
        # the observability budget the operator sees in /metrics. ---
        _llm_call_start = time.monotonic()
        # W6.1 — When caller did NOT specify a model, ask the router. The
        # router is its own gate (AOS_LLM_ROUTER=off returns the default).
        if model is not None:
            target_model = model
        else:
            try:
                from src.llm.router import choose_model
                target_model = choose_model(
                    prompt=prompt, system=system,
                    task_hint=task_hint, risk_hint=risk_hint,
                )
            except Exception:  # pragma: no cover — never break the LLM call
                target_model = self._model

        # --- SAIb guard pass ---
        guard = saib_guard.process(prompt, system)
        if guard.blocked:
            self._record_telemetry(
                model=target_model, via="blocked",
                status="blocked",
                duration_s=time.monotonic() - _llm_call_start,
                error_class="SAIbBlockedError",
            )
            raise SAIbBlockedError(guard.block_reason, guard.classification)

        safe_prompt = guard.safe_prompt
        safe_system = guard.safe_system

        # --- LLM execution ---
        target_tokens = max_tokens or self._max_tokens

        # Infusion takes priority — routes through all 4 LLMs when enabled
        if os.environ.get("AOS_USE_INFUSION", "").lower() == "true":
            from src.infusion.engine import infusion_engine
            text = infusion_engine.complete(safe_prompt, safe_system)
            raw_response = LLMResponse(text=text, model="infusion", via="infusion")
            if guard.mapping:
                unmasked_text = saib_guard.unmask(raw_response.text, guard.mapping)
                return LLMResponse(
                    text=unmasked_text, model="infusion", via="infusion",
                    metadata={"saib_entities": len(guard.entities)},
                )
            return raw_response

        raw_response: Optional[LLMResponse] = None

        # A per-tenant BYOK key (api_key_override) supersedes the platform env
        # key for THIS call — the tenant's own Anthropic account is billed.
        api_key = (api_key_override or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
        force_cli = os.environ.get("AOS_LLM_BACKEND", "").lower() == "cli"

        # Skip the paid API when CLI is forced, or while the API is in a
        # credit/quota cooldown — go straight to the local Claude bridge.
        if api_key and not force_cli and not _api_in_cooldown():
            raw_response = self._try_sdk(
                safe_prompt, safe_system, api_key, target_model, target_tokens,
                cacheable_system=cacheable_system,
            )
            if raw_response is None:
                raw_response = self._try_httpx(
                    safe_prompt, safe_system, api_key, target_model, target_tokens,
                    cacheable_system=cacheable_system,
                )

        # Fallback: local Claude CLI bridge (CLITunnel → `claude -p`, OAuth
        # session, no API credits). Fires when there's no key, CLI is forced,
        # the API is in cooldown, or the API call just failed. A strict BYOK
        # tenant (allow_bridge_fallback=False) never touches the platform bridge.
        if raw_response is None and allow_bridge_fallback:
            claude_bin = shutil.which("claude")
            if claude_bin:
                raw_response = self._try_cli(safe_prompt, safe_system, claude_bin, target_model)

        if raw_response is None:
            self._record_telemetry(
                model=target_model, via="unavailable",
                status="unavailable",
                duration_s=time.monotonic() - _llm_call_start,
                error_class="LLMUnavailableError",
            )
            raise LLMUnavailableError(
                "No LLM endpoint available. Set ANTHROPIC_API_KEY or ensure "
                "the claude CLI is in PATH."
            )

        # Successful call — record telemetry before SAIb unmask transforms
        # the response (token counts are identical either way).
        self._record_telemetry(
            model=raw_response.model, via=raw_response.via,
            status="ok",
            duration_s=time.monotonic() - _llm_call_start,
            input_tokens=raw_response.input_tokens,
            output_tokens=raw_response.output_tokens,
        )

        # --- W6.2 budget accrual + W6.5 per-mission cost attribution ---
        # Compute realised cost once; route it to both the budget tracker
        # (per-customer caps) and the mission-cost tracker (per-mission ledger).
        # Best-effort — never breaks the call.
        if customer_id is not None or mission_id is not None:
            try:
                from src.core.observability.llm_telemetry import estimate_cost_usd
                cost = estimate_cost_usd(
                    raw_response.model,
                    raw_response.input_tokens,
                    raw_response.output_tokens,
                )
                if customer_id is not None:
                    from src.llm.budget import budget_tracker
                    budget_tracker.record_cost(customer_id, cost)
                if mission_id is not None:
                    from src.llm.mission_cost import mission_cost_tracker
                    mission_cost_tracker.record(
                        mission_id,
                        model=raw_response.model,
                        input_tokens=raw_response.input_tokens,
                        output_tokens=raw_response.output_tokens,
                        cost_usd=cost,
                    )
            except Exception:  # pragma: no cover
                pass

        # --- SAIb unmask: restore original values in the response ---
        if guard.mapping:
            unmasked_text = saib_guard.unmask(raw_response.text, guard.mapping)
            return LLMResponse(
                text=unmasked_text,
                model=raw_response.model,
                via=raw_response.via,
                input_tokens=raw_response.input_tokens,
                output_tokens=raw_response.output_tokens,
                metadata={**raw_response.metadata, "saib_entities": len(guard.entities)},
            )

        return raw_response

    # ------------------------------------------------------------------
    # W5.2 — telemetry hook (best-effort; never breaks the LLM call)
    # ------------------------------------------------------------------

    @staticmethod
    def _record_telemetry(
        *,
        model: str,
        via: str,
        status: str,
        duration_s: float,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_class: Optional[str] = None,
    ) -> None:
        try:
            from src.core.observability.llm_telemetry import record_call
            record_call(
                model=model, via=via, status=status,
                duration_s=duration_s,
                input_tokens=input_tokens, output_tokens=output_tokens,
                error_class=error_class,
            )
        except Exception:  # pragma: no cover
            pass

    def is_available(self) -> bool:
        """Return True if at least one LLM endpoint is reachable."""
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip()) or bool(shutil.which("claude"))

    # ------------------------------------------------------------------
    # Private resolution chain
    # ------------------------------------------------------------------

    def _try_sdk(
        self,
        prompt: str,
        system: str,
        api_key: str,
        model: str,
        max_tokens: int,
        cacheable_system: bool = False,
    ) -> Optional[LLMResponse]:
        try:
            import anthropic  # type: ignore[import]
            client = anthropic.Anthropic(api_key=api_key)
            kwargs: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                if cacheable_system:
                    # W6.3 — mark system as cacheable. The API silently no-ops
                    # if the block is below the 1024-token cache minimum, so
                    # this is safe to set unconditionally on opted-in callers.
                    kwargs["system"] = [{
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }]
                    _record_cache_hint(model)
                else:
                    kwargs["system"] = system
            msg = client.messages.create(**kwargs)
            text = msg.content[0].text if msg.content else ""
            usage = getattr(msg, "usage", None)
            return LLMResponse(
                text=text,
                model=model,
                via="anthropic_sdk",
                input_tokens=getattr(usage, "input_tokens", 0),
                output_tokens=getattr(usage, "output_tokens", 0),
            )
        except ImportError:
            logger.debug("anthropic SDK not installed; trying httpx fallback")
            return None
        except Exception as exc:
            if _looks_like_credit_or_quota(str(exc)):
                _mark_api_uncredited(str(exc))
            logger.warning("anthropic SDK call failed: %s", exc)
            return None

    def _try_httpx(
        self,
        prompt: str,
        system: str,
        api_key: str,
        model: str,
        max_tokens: int,
        cacheable_system: bool = False,
    ) -> Optional[LLMResponse]:
        try:
            import httpx  # type: ignore[import]
            body: dict = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system:
                if cacheable_system:
                    body["system"] = [{
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }]
                    _record_cache_hint(model)
                else:
                    body["system"] = system
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=body,
                timeout=120.0,
            )
            if resp.status_code >= 400:
                resp_body = ""
                try:
                    resp_body = resp.text or ""
                except Exception:  # pragma: no cover
                    pass
                # Out-of-credits (400 "credit balance too low"), payment
                # required (402), or rate/quota limit (429) → trip the cooldown
                # so subsequent calls go straight to the local Claude bridge.
                if resp.status_code in (402, 429) or _looks_like_credit_or_quota(resp_body):
                    _mark_api_uncredited(f"HTTP {resp.status_code}: {resp_body[:160]}")
                logger.warning("httpx LLM call failed: %s %s", resp.status_code, resp_body[:200])
                return None
            data = resp.json()
            text = data.get("content", [{}])[0].get("text", "")
            usage = data.get("usage", {})
            return LLMResponse(
                text=text,
                model=model,
                via="httpx",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        except Exception as exc:
            logger.warning("httpx LLM call failed: %s", exc)
            return None

    def _try_cli(
        self,
        prompt: str,
        system: str,
        claude_bin: str,
        model: str,
    ) -> Optional[LLMResponse]:
        """Route through the shared local Claude CLI bridge (CLITunnel).

        Uses the Claude Code OAuth session via `claude -p` — no API credits.
        This is the canonical fallback when the Anthropic API is uncredited.
        `claude_bin` is accepted for backwards-compatibility; the bridge does
        its own PATH lookup.
        """
        try:
            from src.llm.cli_tunnel import cli_tunnel
            text = cli_tunnel.complete(prompt, system)
            if not text or not text.strip():
                logger.warning("claude CLI bridge returned empty output")
                return None
            return LLMResponse(text=text.strip(), model=model, via="claude_cli")
        except Exception as exc:
            logger.warning("claude CLI bridge call failed: %s", exc)
            return None


# Process-level singleton — stateless, safe to share across all modules.
llm_gateway = LLMGateway()
