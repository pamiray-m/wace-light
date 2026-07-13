"""Smart Scraper contracts. Pure Pydantic v2."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ScrapeStatus(str, Enum):
    OK           = "ok"
    BLOCKED      = "blocked"        # SSRF guard rejected the URL
    FETCH_ERROR  = "fetch_error"    # network / HTTP / size / redirect failure
    LLM_ERROR    = "llm_error"      # LLM unavailable or refused
    PARSE_ERROR  = "parse_error"    # LLM replied but not valid JSON


class ScrapeResult(BaseModel):
    """Outcome of one scrape."""

    model_config = ConfigDict(frozen=True)

    url: str
    final_url: str = ""              # after redirects
    status: ScrapeStatus
    title: str = ""
    data: Any = None                 # the extracted structured data (dict/list) when status=OK
    content_chars: int = 0           # how much cleaned text was sent to the LLM
    model: str = ""                  # which LLM produced it
    error: str = ""
    scraped_at: datetime = Field(default_factory=_now)
