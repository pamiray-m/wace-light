"""
Infusion Engine — multi-model LLM orchestration core.

All LLM interactions in AOS route through here when AOS_USE_INFUSION=true.

Pipeline
--------
Phase 1 — Parallel Broadcast
  Send the original prompt simultaneously to all 4 providers:
  Claude · ChatGPT · Gemini · Perplexity

Phase 2 — Synthesis
  Merge the 4 responses into one structured document that preserves
  each model's perspective alongside the original query.

Phase 3 — Sequential Refinement Chain
  Combined → Gemini → Perplexity → ChatGPT → Claude
  Each step receives the previous output and is asked to refine it.
  Claude produces the final authoritative response.

Graceful degradation
  Providers with missing API keys are skipped at both broadcast and
  refinement stages.  If only Claude is available, the engine runs as
  a single-model pass (identical to calling the CLI tunnel directly).
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from src.infusion.contracts import InfusionResult, ProviderResponse
from src.infusion.providers.claude_provider import ClaudeProvider
from src.infusion.providers.gemini_provider import GeminiProvider
from src.infusion.providers.openai_provider import OpenAIProvider
from src.infusion.providers.perplexity_provider import PerplexityProvider

logger = logging.getLogger(__name__)

# Refinement chain order (after the broadcast + combine step)
_REFINEMENT_ORDER = ["gemini", "perplexity", "chatgpt", "claude"]


def _broadcast_prompt(original_prompt: str, system: str) -> str:
    return original_prompt


def _combine_responses(original_prompt: str, responses: list[ProviderResponse]) -> str:
    """
    Merge broadcast responses into a single synthesis document.
    This becomes the input for the first step of the refinement chain.
    """
    sections = [
        "MULTI-MODEL SYNTHESIS\n"
        "=====================\n"
        f"Original query:\n{original_prompt}\n\n"
        "The following AI models have independently analyzed this query:\n"
    ]
    for r in responses:
        label = r.provider.upper()
        sections.append(f"[{label}]\n{r.text}\n")

    sections.append(
        "\nYour task: synthesize the above perspectives into a single comprehensive, "
        "accurate response that integrates the strongest insights from each, resolves "
        "any contradictions, and directly addresses the original query."
    )
    return "\n".join(sections)


def _refinement_prompt(original_prompt: str, current_response: str, step: int) -> str:
    """
    Build the refinement prompt for each step in the chain.
    Steps: 1=Gemini, 2=Perplexity, 3=ChatGPT, 4=Claude (final).
    """
    if step < 4:
        instruction = (
            "Refine and improve this response by: "
            "(1) correcting any inaccuracies or gaps, "
            "(2) improving clarity and precision, "
            "(3) adding any critical missing information, "
            "(4) removing redundancy."
        )
    else:
        instruction = (
            "Produce the definitive final response. "
            "This is the authoritative output for the AOS system. "
            "It must be accurate, complete, directly actionable, and well-structured."
        )

    return (
        f"Original query:\n{original_prompt}\n\n"
        f"Current synthesis:\n{current_response}\n\n"
        f"{instruction}"
    )


class InfusionEngine:
    """
    Core multi-model orchestration engine.

    complete(prompt, system) is a drop-in replacement for any single-model
    LLM call and returns the final Claude-refined response.
    """

    def __init__(self) -> None:
        self._providers = {
            "claude":     ClaudeProvider(),
            "chatgpt":    OpenAIProvider(),
            "gemini":     GeminiProvider(),
            "perplexity": PerplexityProvider(),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(self, prompt: str, system: str = "") -> str:
        """
        Run the full Infusion pipeline and return the final response.

        If only one provider is available the pipeline degrades gracefully
        to a direct single-model call.
        """
        result = self.run(prompt, system)
        return result.final_response

    def run(self, prompt: str, system: str = "") -> InfusionResult:
        """
        Full pipeline returning an InfusionResult with all intermediate steps.
        Useful for observability and debugging.
        """
        # --- Phase 1: Parallel broadcast ---
        broadcast_responses = self._broadcast(prompt, system)
        logger.info(
            "[Infusion] broadcast complete — %d/%d providers responded",
            sum(1 for r in broadcast_responses if r.success),
            len(broadcast_responses),
        )

        # --- Phase 2: Combine ---
        successful = [r for r in broadcast_responses if r.success]
        if not successful:
            # Nothing worked — return a failure message
            return InfusionResult(
                original_prompt=prompt,
                broadcast=broadcast_responses,
                combined_text="",
                refinement_chain=[],
                final_response="Infusion: no LLM providers available.",
            )

        if len(successful) == 1:
            # Only one provider — skip synthesis overhead
            combined = successful[0].text
        else:
            combined = _combine_responses(prompt, successful)

        # --- Phase 3: Refinement chain ---
        refinement_chain, final_response = self._refine(prompt, system, combined)

        return InfusionResult(
            original_prompt=prompt,
            broadcast=broadcast_responses,
            combined_text=combined,
            refinement_chain=refinement_chain,
            final_response=final_response,
        )

    # ------------------------------------------------------------------
    # Phase 1 — Parallel broadcast
    # ------------------------------------------------------------------

    def _broadcast(self, prompt: str, system: str) -> list[ProviderResponse]:
        available = {
            name: p for name, p in self._providers.items() if p.is_available()
        }
        if not available:
            return [ProviderResponse(provider="none", text="", success=False, error="No providers available")]

        results: dict[str, ProviderResponse] = {}

        with ThreadPoolExecutor(max_workers=len(available)) as pool:
            futures = {
                pool.submit(self._call_provider, name, p, prompt, system): name
                for name, p in available.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                results[name] = future.result()

        # Return in consistent order
        return [results[n] for n in ["claude", "chatgpt", "gemini", "perplexity"] if n in results]

    def _call_provider(
        self, name: str, provider, prompt: str, system: str
    ) -> ProviderResponse:
        try:
            text = provider.complete(prompt, system)
            logger.debug("[Infusion] %s responded (%d chars)", name, len(text))
            return ProviderResponse(provider=name, text=text, success=True)
        except Exception as exc:
            logger.warning("[Infusion] %s failed: %s", name, exc)
            return ProviderResponse(provider=name, text="", success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Phase 3 — Sequential refinement chain
    # ------------------------------------------------------------------

    def _refine(
        self, original_prompt: str, system: str, combined: str
    ) -> tuple[list[ProviderResponse], str]:
        chain: list[ProviderResponse] = []
        current = combined
        step = 0

        for provider_name in _REFINEMENT_ORDER:
            provider = self._providers.get(provider_name)
            if provider is None or not provider.is_available():
                logger.debug("[Infusion] refinement: skipping %s (unavailable)", provider_name)
                continue

            step += 1
            ref_prompt = _refinement_prompt(original_prompt, current, step)

            try:
                refined = provider.complete(ref_prompt, system)
                logger.debug(
                    "[Infusion] refinement step %d (%s) complete (%d chars)",
                    step, provider_name, len(refined),
                )
                record = ProviderResponse(provider=provider_name, text=refined, success=True)
                chain.append(record)
                current = refined
            except Exception as exc:
                logger.warning("[Infusion] refinement %s failed: %s", provider_name, exc)
                chain.append(ProviderResponse(
                    provider=provider_name, text="", success=False, error=str(exc)
                ))
                # Keep current unchanged and continue to next step

        return chain, current


# Process-level singleton
infusion_engine = InfusionEngine()
