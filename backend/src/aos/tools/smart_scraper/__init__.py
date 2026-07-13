"""
AOS-1 Smart Scraper — LLM-powered structured web scraping, built natively.

The capability of scrapegraphai (extract structured data from a web page with a
plain-English prompt) without the library: no langchain, no Playwright/evasion
deps, and — critically — **no third-party telemetry**. It uses AOS-1's own
`llm_gateway`, `httpx` (already a dependency), and the Python standard library
HTML parser. The only place page content goes is the LLM you already use.

Pipeline: fetch (SSRF-guarded) -> clean HTML to text -> prompt the LLM with the
extraction instruction + optional JSON schema -> parse/return structured JSON.

Entry point: `smart_scraper.scrape(url, prompt, schema=...)`.
"""

from .contracts import ScrapeStatus, ScrapeResult
from .fetcher import FetchError, SSRFError, fetch
from .extractor import html_to_text
from .service import SmartScraperService, smart_scraper
from .leads import (
    LEAD_SCHEMA, LEAD_INSTRUCTION, scrape_leads, scrape_leads_many, flatten_leads,
)

__all__ = [
    "ScrapeStatus",
    "ScrapeResult",
    "FetchError",
    "SSRFError",
    "fetch",
    "html_to_text",
    "SmartScraperService",
    "smart_scraper",
    "LEAD_SCHEMA",
    "LEAD_INSTRUCTION",
    "scrape_leads",
    "scrape_leads_many",
    "flatten_leads",
]
