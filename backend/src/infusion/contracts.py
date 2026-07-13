"""
Infusion — data contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderResponse:
    provider: str          # "claude" | "chatgpt" | "gemini" | "perplexity"
    text: str
    success: bool
    error: Optional[str] = None


@dataclass
class InfusionResult:
    original_prompt: str
    broadcast: list[ProviderResponse]          # 4 parallel responses
    combined_text: str                          # structured merge of broadcast
    refinement_chain: list[ProviderResponse]   # gemini → perplexity → chatgpt → claude
    final_response: str
