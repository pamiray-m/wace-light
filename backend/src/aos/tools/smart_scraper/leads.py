"""
Lead extraction on top of the Smart Scraper.

Given a page (a single company site OR a directory/listing of many companies),
the LLM returns a normalized list of B2B company leads with optional contacts.
This is generic extraction only — it knows nothing about Prospect/ROS/Nexus or
lawful basis; that governance lives in the Prospect engine.
"""

from __future__ import annotations

from typing import Optional

from .contracts import ScrapeResult, ScrapeStatus
from .service import smart_scraper

# JSON schema the LLM is asked to fill. A LIST so directory pages work too.
LEAD_SCHEMA: dict = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "company": {"type": "string"},
            "website": {"type": ["string", "null"]},
            "industry": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "location": {"type": ["string", "null"]},
            "employees": {"type": ["integer", "null"]},
            "contacts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "title": {"type": ["string", "null"]},
                        "email": {"type": ["string", "null"]},
                        "linkedin": {"type": ["string", "null"]},
                        "phone": {"type": ["string", "null"]},
                    },
                },
            },
        },
        "required": ["company"],
    },
}

LEAD_INSTRUCTION = (
    "Extract every distinct company or organization on this page that could be a "
    "B2B sales lead. For each, capture its name, website, industry, a one-line "
    "description, location, approximate employee count if stated, and any named "
    "business contacts (name, job title, business email, LinkedIn, phone) that "
    "appear ON THE PAGE. Only include data actually present — use null for "
    "anything not shown, and do not guess emails or contact details."
)


def scrape_leads(
    url: str,
    *,
    instruction: Optional[str] = None,
    max_chars: int = 14_000,
    model: Optional[str] = None,
) -> ScrapeResult:
    """Scrape one page for company leads. `result.data` is a list of lead dicts."""
    res = smart_scraper.scrape(
        url, instruction or LEAD_INSTRUCTION,
        schema=LEAD_SCHEMA, max_chars=max_chars, model=model,
    )
    # Normalize: ensure data is a list when OK (the LLM may return a bare object).
    if res.status is ScrapeStatus.OK and isinstance(res.data, dict):
        res = res.model_copy(update={"data": [res.data]})
    return res


def scrape_leads_many(
    urls: list[str],
    *,
    instruction: Optional[str] = None,
    max_chars: int = 14_000,
    model: Optional[str] = None,
) -> list[ScrapeResult]:
    """Scrape several pages; one ScrapeResult per URL (failures included)."""
    return [
        scrape_leads(u, instruction=instruction, max_chars=max_chars, model=model)
        for u in urls
    ]


def flatten_leads(results: list[ScrapeResult]) -> list[dict]:
    """Flatten OK scrape results into per-contact lead candidate dicts.

    Each company with N named contacts yields N candidates; a company with no
    contacts yields one company-level candidate (no email). Carries the source
    URL so provenance is preserved.
    """
    out: list[dict] = []
    for res in results:
        if res.status is not ScrapeStatus.OK or not isinstance(res.data, list):
            continue
        for company in res.data:
            if not isinstance(company, dict):
                continue
            base = {
                "company": (company.get("company") or "").strip() or None,
                "industry": company.get("industry"),
                "geo": company.get("location"),
                "website": company.get("website"),
                "employees": company.get("employees"),
                "source_ref": res.final_url or res.url,
            }
            contacts = company.get("contacts") or []
            if isinstance(contacts, list) and contacts:
                for c in contacts:
                    if not isinstance(c, dict):
                        continue
                    out.append({
                        **base,
                        "full_name": (c.get("name") or "").strip(),
                        "title": c.get("title"),
                        "email": c.get("email"),
                        "linkedin_url": c.get("linkedin"),
                    })
            else:
                out.append({**base, "full_name": "", "title": None,
                            "email": None, "linkedin_url": None})
    return out
