"""
Voundry workspace blueprints — the deterministic (discipline × vertical) registry.

Every contributor is matched to a ROLE on a venture. A role is a DISCIPLINE
(marketing, engineering, sales…) practised inside a VERTICAL (retail, telecom,
fintech…). The two together determine the workspace: the tools to connect, the
AI agents allocated to assist, the resources to draw on, and the checklist to
work through.

Design (mirrors scoring.py / credits.py): a pure, deterministic registry that
never explodes combinatorially. Each discipline has a BASE kit; each vertical
carries per-discipline OVERLAYS layered on top. So:

    blueprint_for("marketing", "retail")  = MARKETING base + RETAIL·marketing overlay
    blueprint_for("marketing", "telecom") = MARKETING base + TELECOM·marketing overlay

which are genuinely different workspaces without hand-authoring an N×M matrix.

Tool connect-status is resolved at runtime (env probe) in a thin layer on top of
this pure registry — the registry itself stays deterministic and testable.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Discipline(str, Enum):
    ENGINEERING = "engineering"
    DESIGN      = "design"
    PRODUCT     = "product"
    MARKETING   = "marketing"
    SALES       = "sales"
    OPERATIONS  = "operations"
    RESEARCH    = "research"
    DATA        = "data"
    FINANCE     = "finance"
    LEGAL       = "legal"
    SUPPORT     = "support"
    CONTENT     = "content"
    IT_OPS      = "it_ops"      # IT / Telecom BSS operations — the WACE beachhead


class Vertical(str, Enum):
    RETAIL        = "retail"
    TELECOM       = "telecom"
    FINTECH       = "fintech"
    HEALTHCARE    = "healthcare"
    SAAS          = "saas"
    ECOMMERCE     = "ecommerce"
    MEDIA         = "media"
    EDUCATION     = "education"
    MANUFACTURING = "manufacturing"
    GENERIC       = "generic"


# Free-form work_unit.role_type strings → a canonical Discipline.
_DISCIPLINE_ALIASES: dict[str, Discipline] = {
    "product": Discipline.PRODUCT, "pm": Discipline.PRODUCT,
    "engineering": Discipline.ENGINEERING, "eng": Discipline.ENGINEERING,
    "backend": Discipline.ENGINEERING, "frontend": Discipline.ENGINEERING,
    "fullstack": Discipline.ENGINEERING, "dev": Discipline.ENGINEERING,
    "design": Discipline.DESIGN, "ux": Discipline.DESIGN, "ui": Discipline.DESIGN,
    "marketing": Discipline.MARKETING, "growth": Discipline.MARKETING,
    "sales": Discipline.SALES, "bizdev": Discipline.SALES, "business_development": Discipline.SALES,
    "operations": Discipline.OPERATIONS, "ops": Discipline.OPERATIONS,
    "research": Discipline.RESEARCH, "market_research": Discipline.RESEARCH,
    "data": Discipline.DATA, "analytics": Discipline.DATA, "data_science": Discipline.DATA,
    "finance": Discipline.FINANCE, "accounting": Discipline.FINANCE,
    "legal": Discipline.LEGAL, "compliance": Discipline.LEGAL, "governance": Discipline.LEGAL,
    "support": Discipline.SUPPORT, "customer_success": Discipline.SUPPORT,
    "content": Discipline.CONTENT, "copywriting": Discipline.CONTENT,
    "it_ops": Discipline.IT_OPS, "itops": Discipline.IT_OPS, "bss_ops": Discipline.IT_OPS,
    "bss": Discipline.IT_OPS, "noc": Discipline.IT_OPS, "sre": Discipline.IT_OPS,
    "incident": Discipline.IT_OPS, "incident_management": Discipline.IT_OPS,
    "network_operations": Discipline.IT_OPS, "it_operations": Discipline.IT_OPS,
    "service_desk": Discipline.IT_OPS, "l2_support": Discipline.IT_OPS,
}


def discipline_from_role_type(role_type: str) -> Discipline:
    """Map a work unit's free-form role_type onto a canonical Discipline."""
    key = (role_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _DISCIPLINE_ALIASES.get(key, Discipline.PRODUCT)


# Vertical keyword classifier — checked in order (specific before generic).
_VERTICAL_KEYWORDS: list[tuple[Vertical, tuple[str, ...]]] = [
    (Vertical.HEALTHCARE,   ("health", "clinical", "patient", "medical", "pharma", "hospital", "care ")),
    (Vertical.TELECOM,      ("telecom", "carrier", "5g", "network operator", "mobile operator", "isp", "connectivity")),
    (Vertical.FINTECH,      ("fintech", "bank", "payment", "lending", "trading", "wealth", "insurance", "financial")),
    (Vertical.ECOMMERCE,    ("ecommerce", "e-commerce", "online store", "dtc", "d2c", "online marketplace")),
    (Vertical.RETAIL,       ("retail", "store", "shopper", "merchandis", "point of sale", "brick-and-mortar", "consumer goods")),
    (Vertical.EDUCATION,    ("education", "edtech", "learning", "student", "course", "curriculum", "training")),
    (Vertical.MANUFACTURING,("manufactur", "factory", "supply chain", "industrial", "logistics", "warehouse")),
    (Vertical.MEDIA,        ("media", "publishing", "streaming", "entertainment", "newsroom", "creator economy")),
    (Vertical.SAAS,         ("saas", "b2b software", "software platform", "subscription software", "developer tool", "api platform")),
]


def derive_vertical(*texts: str) -> Vertical:
    """Deterministically classify a venture's vertical from its market/idea text."""
    blob = " ".join(t for t in texts if t).lower()
    if not blob.strip():
        return Vertical.GENERIC
    for vertical, keywords in _VERTICAL_KEYWORDS:
        if any(k in blob for k in keywords):
            return vertical
    return Vertical.GENERIC


# ---------------------------------------------------------------------------
# Models (computed, not persisted)
# ---------------------------------------------------------------------------


class WorkspaceTool(BaseModel):
    key:          str
    name:         str
    purpose:      str
    kind:         str   # "builtin" | "external" | "env"
    env_var:      Optional[str] = None
    link:         Optional[str] = None
    connect_hint: str = ""
    status:       str = "available"   # resolved at runtime: connected|available|needs_setup


class WorkspaceAgent(BaseModel):
    key:        str
    name:       str
    does:       str
    powered_by: str   # "content-engine" | "smart-scraper" | "llm-gateway" | "assistant"
    live:       bool  # True when backed by a real, wired AOS capability


class WorkspaceResource(BaseModel):
    key:     str
    title:   str
    kind:    str   # "playbook" | "template" | "checklist" | "reference"
    summary: str


class WorkspaceBlueprint(BaseModel):
    discipline: Discipline
    vertical:   Vertical
    headline:   str
    tools:      list[WorkspaceTool] = Field(default_factory=list)
    agents:     list[WorkspaceAgent] = Field(default_factory=list)
    resources:  list[WorkspaceResource] = Field(default_factory=list)
    checklist:  list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Discipline base kits
# ---------------------------------------------------------------------------


def _tool(key, name, purpose, kind, env_var=None, link=None, hint="") -> WorkspaceTool:
    return WorkspaceTool(key=key, name=name, purpose=purpose, kind=kind,
                         env_var=env_var, link=link, connect_hint=hint)


def _agent(key, name, does, powered_by, live) -> WorkspaceAgent:
    return WorkspaceAgent(key=key, name=name, does=does, powered_by=powered_by, live=live)


def _res(key, title, kind, summary) -> WorkspaceResource:
    return WorkspaceResource(key=key, title=title, kind=kind, summary=summary)


DISCIPLINE_KITS: dict[Discipline, dict] = {
    Discipline.IT_OPS: {
        "tools": [
            _tool("incident_queue", "Incident Queue", "Open incidents & change requests", "env", env_var="REMEDY_BASE_URL", hint="Operator connects Remedy/ServiceNow"),
            _tool("sql_console", "SQL Console", "Run approved read-only queries", "env", env_var="OPS_SQL_DSN", hint="Operator connects a read-only DB"),
            _tool("knowledge_base", "Knowledge Base", "Runbooks & known-error DB", "env", env_var="OPS_KB_URL", hint="Connect SharePoint / Confluence"),
            _tool("monitoring", "Monitoring", "System health & alarms at a glance", "builtin"),
        ],
        "agents": [
            _agent("incident_analyst", "Incident Analyst", "Triages an incident — severity, impact, likely cause, next steps", "llm-gateway", True),
            _agent("rca_investigator", "RCA Investigator", "Builds a root-cause hypothesis from tickets, logs & context", "llm-gateway", True),
            _agent("change_risk_reviewer", "Change-risk Reviewer", "Scores a change request's risk & blast radius before approval", "llm-gateway", True),
            _agent("report_generator", "Report Generator", "Turns the shift's activity into a clean ops report", "content-engine", True),
        ],
        "resources": [
            _res("runbooks", "Runbooks", "playbook", "Step-by-step procedures for common incidents"),
            _res("known_errors", "Known-Error DB", "reference", "Known issues and their workarounds"),
            _res("escalation", "Escalation Matrix", "reference", "Who to page, when, and how"),
        ],
        "checklist": [
            "Review open incidents and priorities for the shift",
            "Triage new incidents — severity, impact, owner",
            "Investigate root cause with the RCA agent",
            "Review pending changes for risk before approval",
            "Log actions and hand off with a shift report",
        ],
    },
    Discipline.MARKETING: {
        "tools": [
            _tool("content_engine", "Content Studio", "Draft governed, on-brand posts", "builtin", hint="Built in — open the Content Studio"),
            _tool("social", "Social Scheduler", "Schedule & publish to LinkedIn", "env", env_var="LINKEDIN_ACCESS_TOKEN", hint="Operator connects LinkedIn"),
            _tool("email", "Email Campaigns", "Send campaign email", "env", env_var="RESEND_API_KEY", hint="Operator connects Resend"),
            _tool("analytics", "Reach Analytics", "Track reach & engagement", "builtin"),
        ],
        "agents": [
            _agent("content_drafter", "Content Drafter", "Drafts posts & campaigns to your brief", "content-engine", True),
            _agent("audience_researcher", "Audience Researcher", "Finds & profiles your target audience", "smart-scraper", True),
            _agent("campaign_analyst", "Campaign Analyst", "Reads results and suggests the next move", "llm-gateway", True),
        ],
        "resources": [
            _res("messaging", "Messaging Framework", "template", "Positioning, value props, tone of voice"),
            _res("calendar", "Content Calendar", "template", "A 4-week publishing plan you fill in"),
            _res("channel_play", "Channel Playbook", "playbook", "Where and how to reach your audience"),
        ],
        "checklist": [
            "Define the target audience and their #1 problem",
            "Draft the positioning and top 3 messages",
            "Build a 4-week content calendar",
            "Launch the first campaign",
            "Measure reach and report what worked",
        ],
    },
    Discipline.SALES: {
        "tools": [
            _tool("crm", "Pipeline CRM", "Track leads & deals", "builtin"),
            _tool("outreach", "Outreach Sequencer", "Run email/LinkedIn sequences", "env", env_var="LINKEDIN_ACCESS_TOKEN", hint="Operator connects outreach"),
            _tool("proposal", "Proposal Builder", "Generate proposals & quotes", "builtin"),
            _tool("call_notes", "Call Notes", "Log calls & next steps", "builtin"),
        ],
        "agents": [
            _agent("prospector", "Prospector", "Finds and qualifies leads that fit the ICP", "smart-scraper", True),
            _agent("outreach_writer", "Outreach Writer", "Drafts personalised outreach", "content-engine", True),
            _agent("deal_coach", "Deal Coach", "Suggests next steps to move a deal", "llm-gateway", True),
        ],
        "resources": [
            _res("icp", "Ideal Customer Profile", "template", "Who to sell to and why"),
            _res("script", "Outreach Scripts", "template", "First-touch and follow-up templates"),
            _res("objection", "Objection Handling", "playbook", "Common objections and responses"),
        ],
        "checklist": [
            "Define the ideal customer profile",
            "Build a target list of 25 accounts",
            "Run first-touch outreach",
            "Book and run discovery calls",
            "Send the first proposal",
        ],
    },
    Discipline.ENGINEERING: {
        "tools": [
            _tool("repo", "Code Repository", "Source control & pull requests", "external", link="https://github.com", hint="Connect your GitHub"),
            _tool("issues", "Issue Tracker", "Track work & bugs", "builtin"),
            _tool("api_console", "API Console", "Test the venture's APIs", "builtin"),
            _tool("ci", "CI / Checks", "Automated tests on each change", "external", link="https://github.com", hint="Runs on your repo"),
        ],
        "agents": [
            _agent("code_reviewer", "Code Reviewer", "Reviews your changes for bugs & clarity", "llm-gateway", True),
            _agent("docs_writer", "Docs Writer", "Turns code into readable docs", "content-engine", True),
            _agent("test_helper", "Test Helper", "Suggests test cases for your change", "llm-gateway", True),
        ],
        "resources": [
            _res("arch", "Architecture Notes", "reference", "How the venture's system fits together"),
            _res("standards", "Engineering Standards", "playbook", "How we build, review, and ship"),
            _res("evidence", "Evidence Checklist", "checklist", "What to attach when you submit"),
        ],
        "checklist": [
            "Read the architecture notes and the work brief",
            "Scope the change and open an issue",
            "Build it with tests",
            "Open a pull request with evidence links",
            "Address review and submit for credit",
        ],
    },
    Discipline.DESIGN: {
        "tools": [
            _tool("figma", "Design Canvas", "Design screens & flows", "external", link="https://figma.com", hint="Connect your Figma"),
            _tool("design_system", "Design System", "Shared components & tokens", "builtin"),
            _tool("assets", "Asset Library", "Logos, images, brand assets", "builtin"),
        ],
        "agents": [
            _agent("ux_researcher", "UX Researcher", "Summarises user needs & patterns", "llm-gateway", True),
            _agent("copy_helper", "Microcopy Helper", "Drafts UI copy & labels", "content-engine", True),
        ],
        "resources": [
            _res("brand", "Brand Kit", "reference", "Colours, type, logo usage"),
            _res("patterns", "UX Patterns", "reference", "Reusable interaction patterns"),
            _res("handoff", "Handoff Checklist", "checklist", "What engineering needs from you"),
        ],
        "checklist": [
            "Review the brand kit and the brief",
            "Sketch the flow and key screens",
            "Design to the design system",
            "Prepare a clean handoff",
            "Submit with a shareable link",
        ],
    },
    Discipline.PRODUCT: {
        "tools": [
            _tool("roadmap", "Roadmap Board", "Plan and prioritise work", "builtin"),
            _tool("interviews", "User Interviews", "Log & synthesise user feedback", "builtin"),
            _tool("spec", "Spec Builder", "Write clear specs", "builtin"),
            _tool("analytics", "Product Analytics", "See how the product is used", "builtin"),
        ],
        "agents": [
            _agent("spec_writer", "Spec Writer", "Turns your intent into a clear spec", "content-engine", True),
            _agent("insight_synth", "Insight Synthesiser", "Finds themes in user feedback", "llm-gateway", True),
        ],
        "resources": [
            _res("prd", "PRD Template", "template", "A one-page product requirements doc"),
            _res("prioritise", "Prioritisation Guide", "playbook", "Decide what to build first"),
        ],
        "checklist": [
            "Clarify the problem and the user",
            "Write a one-page spec",
            "Prioritise the smallest useful slice",
            "Align engineering & design",
            "Define how you'll measure success",
        ],
    },
    Discipline.OPERATIONS: {
        "tools": [
            _tool("processes", "Process Docs", "Document how things run", "builtin"),
            _tool("vendors", "Vendor Tracker", "Track suppliers & tools", "builtin"),
            _tool("scheduler", "Scheduler", "Plan tasks & deadlines", "builtin"),
        ],
        "agents": [
            _agent("process_writer", "Process Writer", "Documents a repeatable process", "content-engine", True),
            _agent("ops_analyst", "Ops Analyst", "Spots bottlenecks and fixes", "llm-gateway", True),
        ],
        "resources": [
            _res("sop", "SOP Template", "template", "Standard operating procedure format"),
            _res("runbook", "Runbook", "playbook", "What to do when things break"),
        ],
        "checklist": [
            "Map the current process",
            "Find the biggest bottleneck",
            "Write the improved SOP",
            "Roll it out and measure",
            "Submit the runbook",
        ],
    },
    Discipline.RESEARCH: {
        "tools": [
            _tool("scraper", "Web Research", "Gather sources from the web", "builtin", hint="Powered by the AOS Smart Scraper"),
            _tool("library", "Source Library", "Save & organise sources", "builtin"),
            _tool("synthesis", "Synthesis Board", "Turn sources into findings", "builtin"),
        ],
        "agents": [
            _agent("web_researcher", "Web Researcher", "Gathers and cites sources for you", "smart-scraper", True),
            _agent("synthesiser", "Synthesiser", "Turns sources into clear findings", "llm-gateway", True),
        ],
        "resources": [
            _res("brief", "Research Brief", "template", "Question, scope, and method"),
            _res("citation", "Citation Standard", "reference", "How to record and cite sources"),
        ],
        "checklist": [
            "Write the research question and scope",
            "Gather and cite credible sources",
            "Synthesise the findings",
            "State the recommendation",
            "Submit with the source list",
        ],
    },
    Discipline.DATA: {
        "tools": [
            _tool("query", "Query Console", "Query the venture's data", "builtin"),
            _tool("dashboard", "Dashboards", "Build & share dashboards", "builtin"),
            _tool("pipeline", "Pipeline Monitor", "Watch data pipelines", "builtin"),
        ],
        "agents": [
            _agent("query_helper", "Query Helper", "Drafts queries from a plain-English ask", "llm-gateway", True),
            _agent("insight_finder", "Insight Finder", "Surfaces patterns worth acting on", "llm-gateway", True),
        ],
        "resources": [
            _res("schema", "Data Dictionary", "reference", "What the tables and fields mean"),
            _res("metrics", "Metric Definitions", "reference", "How each metric is calculated"),
        ],
        "checklist": [
            "Understand the question behind the ask",
            "Find the right data and check quality",
            "Build the analysis or dashboard",
            "Explain the finding in plain words",
            "Submit with the query and evidence",
        ],
    },
    Discipline.FINANCE: {
        "tools": [
            _tool("ledger", "Ledger View", "See the venture's cost ledger", "builtin"),
            _tool("model", "Model Builder", "Build financial models", "builtin"),
            _tool("invoicing", "Invoicing", "Issue & track invoices", "env", env_var="STRIPE_API_KEY", hint="Operator connects Stripe"),
        ],
        "agents": [
            _agent("model_helper", "Model Helper", "Builds and checks financial models", "llm-gateway", True),
        ],
        "resources": [
            _res("model_tmpl", "Model Template", "template", "Revenue, cost, and runway model"),
            _res("unit_econ", "Unit Economics Guide", "playbook", "Make the numbers make sense"),
        ],
        "checklist": [
            "Gather the cost and revenue inputs",
            "Build the model",
            "Sanity-check the unit economics",
            "Write the one-paragraph summary",
            "Submit the model",
        ],
    },
    Discipline.LEGAL: {
        "tools": [
            _tool("templates", "Contract Templates", "Draft standard agreements", "builtin"),
            _tool("ip_registry", "IP Registry", "Track the venture's IP", "builtin", hint="Built in — the venture IP registry"),
            _tool("compliance", "Compliance Checklist", "Track legal obligations", "builtin"),
        ],
        "agents": [
            _agent("clause_helper", "Clause Helper", "Drafts and explains clauses (not legal advice)", "llm-gateway", True),
        ],
        "resources": [
            _res("nda_tmpl", "Agreement Templates", "template", "NDA, MSA, and DPA starting points"),
            _res("compliance_ref", "Compliance Reference", "reference", "Obligations by jurisdiction"),
        ],
        "checklist": [
            "Identify the legal need",
            "Draft from the right template",
            "Flag anything that needs counsel",
            "Record it in the IP/compliance registry",
            "Submit the draft for review",
        ],
    },
    Discipline.SUPPORT: {
        "tools": [
            _tool("tickets", "Ticket Queue", "Handle customer requests", "builtin"),
            _tool("kb", "Knowledge Base", "Write & maintain help articles", "builtin"),
            _tool("macros", "Macro Library", "Reusable replies", "builtin"),
        ],
        "agents": [
            _agent("reply_drafter", "Reply Drafter", "Drafts on-brand support replies", "content-engine", True),
            _agent("kb_writer", "KB Writer", "Turns tickets into help articles", "content-engine", True),
        ],
        "resources": [
            _res("tone", "Support Tone Guide", "reference", "How we talk to customers"),
            _res("escalate", "Escalation Playbook", "playbook", "When and how to escalate"),
        ],
        "checklist": [
            "Learn the product and common issues",
            "Clear the ticket queue",
            "Write help articles for repeat questions",
            "Track satisfaction",
            "Submit your summary",
        ],
    },
    Discipline.CONTENT: {
        "tools": [
            _tool("content_engine", "Content Studio", "Write governed, on-brand content", "builtin", hint="Built in — the Content Studio"),
            _tool("editorial", "Editorial Calendar", "Plan the content pipeline", "builtin"),
            _tool("assets", "Asset Library", "Images & media", "builtin"),
        ],
        "agents": [
            _agent("writer", "Writer", "Drafts long- and short-form content", "content-engine", True),
            _agent("editor", "Editor", "Tightens and fact-checks drafts", "llm-gateway", True),
        ],
        "resources": [
            _res("style", "Style Guide", "reference", "Voice, grammar, and formatting"),
            _res("brief_tmpl", "Content Brief", "template", "Goal, audience, and key points"),
        ],
        "checklist": [
            "Take the content brief",
            "Draft with the Content Studio",
            "Edit and fact-check",
            "Get it through compliance review",
            "Submit the finished piece",
        ],
    },
}


# ---------------------------------------------------------------------------
# Vertical overlays — additions layered onto the discipline base
# ---------------------------------------------------------------------------

# vertical → { discipline → {"tools": [...], "resources": [...], "checklist": [...]} }
VERTICAL_OVERLAYS: dict[Vertical, dict[Discipline, dict]] = {
    Vertical.RETAIL: {
        Discipline.MARKETING: {
            "tools": [
                _tool("merchant_feed", "Merchant Feed", "Sync products to Google/Meta shopping", "external", link="https://merchants.google.com", hint="Connect a merchant centre"),
                _tool("seasonal", "Seasonal Planner", "Plan around retail seasons & promos", "builtin"),
                _tool("price_watch", "Price Watch", "Monitor competitor prices", "builtin", hint="Powered by the AOS Smart Scraper"),
            ],
            "resources": [
                _res("retail_cal", "Retail Seasonal Calendar", "reference", "Key retail dates & promo windows"),
                _res("promo_play", "Promotions Playbook", "playbook", "Run discounts without eroding margin"),
            ],
            "checklist": ["Plan around the next retail season/promo window"],
        },
        Discipline.SALES: {
            "resources": [_res("retail_buyers", "Retail Buyer Guide", "playbook", "How retail buyers evaluate & purchase")],
        },
    },
    Vertical.TELECOM: {
        Discipline.MARKETING: {
            "tools": [
                _tool("abm", "ABM Console", "Account-based marketing for B2B telecom", "builtin"),
                _tool("whitepaper", "Whitepaper Builder", "Produce technical thought-leadership", "builtin", hint="Powered by the Content Studio"),
                _tool("reg_review", "Regulatory Review", "Check messaging against telecom rules", "builtin"),
            ],
            "resources": [
                _res("abm_play", "B2B ABM Playbook", "playbook", "Win named telecom accounts"),
                _res("tech_content", "Technical Content Guide", "reference", "Write for network engineers & CTOs"),
            ],
            "checklist": ["Tailor messaging for long B2B telecom sales cycles"],
        },
        Discipline.SALES: {
            "resources": [_res("telco_procure", "Telecom Procurement Guide", "playbook", "Navigate carrier procurement & RFPs")],
        },
        Discipline.ENGINEERING: {
            "resources": [_res("telco_stds", "Telecom Standards", "reference", "Relevant network & interoperability standards")],
        },
        Discipline.IT_OPS: {
            "tools": [
                _tool("bss_health", "CBS/BSS Health", "Billing & charging system health indicators", "builtin"),
                _tool("alarm_feed", "Alarm Feed", "Customer-impacting network alarms", "builtin"),
            ],
            "resources": [
                _res("bss_runbook", "BSS Runbooks", "playbook", "Billing/charging incident procedures"),
            ],
            "checklist": ["Watch CBS/BSS health and customer-impacting alarms this shift"],
        },
    },
    Vertical.FINTECH: {
        Discipline.MARKETING: {
            "tools": [_tool("compliance_copy", "Compliance Copy Check", "Screen claims for financial-promotion rules", "builtin")],
            "resources": [_res("fin_promo", "Financial Promotion Rules", "reference", "What you can and can't claim")],
            "checklist": ["Clear all claims through financial-promotion review"],
        },
        Discipline.LEGAL: {
            "resources": [_res("fin_reg", "Financial Regulation Map", "reference", "Licensing & conduct obligations")],
        },
        Discipline.ENGINEERING: {
            "resources": [_res("pci", "Security & PCI Notes", "reference", "Handling payments & sensitive data")],
        },
    },
    Vertical.HEALTHCARE: {
        Discipline.MARKETING: {
            "resources": [_res("hc_claims", "Health Claims Guide", "reference", "Substantiating health-related claims")],
            "checklist": ["Ensure claims are evidence-backed and compliant"],
        },
        Discipline.LEGAL: {
            "resources": [_res("hipaa", "Data Protection (Health)", "reference", "HIPAA/GDPR-health handling")],
        },
        Discipline.ENGINEERING: {
            "resources": [_res("phi", "PHI Handling", "reference", "Protecting patient health information")],
        },
    },
    Vertical.SAAS: {
        Discipline.MARKETING: {
            "tools": [_tool("plg", "Product-Led Growth", "Instrument signups & activation", "builtin")],
            "resources": [_res("plg_play", "PLG Playbook", "playbook", "Grow through the product itself")],
        },
        Discipline.SALES: {
            "resources": [_res("saas_metrics", "SaaS Sales Metrics", "reference", "MRR, churn, expansion, CAC/LTV")],
        },
    },
    Vertical.ECOMMERCE: {
        Discipline.MARKETING: {
            "tools": [
                _tool("catalog", "Catalog Ads", "Run dynamic product ads", "external", link="https://business.facebook.com", hint="Connect an ad account"),
                _tool("cro", "Conversion Optimiser", "Improve the storefront funnel", "builtin"),
            ],
            "resources": [_res("cro_play", "Conversion Playbook", "playbook", "Lift store conversion rate")],
        },
    },
    Vertical.MEDIA: {
        Discipline.CONTENT: {
            "resources": [_res("distrib", "Distribution Playbook", "playbook", "Get content seen across channels")],
        },
    },
    Vertical.EDUCATION: {
        Discipline.PRODUCT: {
            "resources": [_res("pedagogy", "Learning Design Guide", "reference", "Design for real learning outcomes")],
        },
    },
    Vertical.MANUFACTURING: {
        Discipline.OPERATIONS: {
            "tools": [_tool("supply", "Supply Chain Tracker", "Track suppliers & lead times", "builtin")],
            "resources": [_res("supply_play", "Supply Chain Playbook", "playbook", "Keep the line running")],
        },
    },
}


_VERTICAL_HEADLINES: dict[Vertical, str] = {
    Vertical.RETAIL: "retail — seasonal, price-sensitive, consumer-facing",
    Vertical.TELECOM: "telecom — technical, B2B, long sales cycles",
    Vertical.FINTECH: "fintech — regulated, trust-critical",
    Vertical.HEALTHCARE: "healthcare — compliant, evidence-led",
    Vertical.SAAS: "SaaS — product-led, metrics-driven",
    Vertical.ECOMMERCE: "e-commerce — conversion-driven, direct-to-consumer",
    Vertical.MEDIA: "media — distribution-driven, audience-first",
    Vertical.EDUCATION: "education — outcome-focused",
    Vertical.MANUFACTURING: "manufacturing — supply-chain-driven",
    Vertical.GENERIC: "general venture",
}


def blueprint_for(discipline: Discipline, vertical: Vertical) -> WorkspaceBlueprint:
    """Compose the deterministic workspace blueprint for a (discipline, vertical).

    Base discipline kit + vertical overlay. Pure — connect-status is resolved
    separately by resolve_status()."""
    base = DISCIPLINE_KITS[discipline]
    overlay = VERTICAL_OVERLAYS.get(vertical, {}).get(discipline, {})

    tools = [t.model_copy(deep=True) for t in base["tools"]]
    tools += [t.model_copy(deep=True) for t in overlay.get("tools", [])]
    agents = [a.model_copy(deep=True) for a in base["agents"]]
    resources = [r.model_copy(deep=True) for r in base["resources"]]
    resources += [r.model_copy(deep=True) for r in overlay.get("resources", [])]
    checklist = list(base["checklist"]) + list(overlay.get("checklist", []))

    headline = (
        f"{discipline.value.title()} · {_VERTICAL_HEADLINES.get(vertical, vertical.value)}"
    )
    return WorkspaceBlueprint(
        discipline=discipline, vertical=vertical, headline=headline,
        tools=tools, agents=agents, resources=resources, checklist=checklist,
    )


# ---------------------------------------------------------------------------
# Requestable agent catalog — additional role-relevant skills a contributor can
# add to their workspace for more capability, beyond the default allocated set.
# Curated per discipline (pre-vetted as role-appropriate), so requesting one is
# self-serve but recorded.
# ---------------------------------------------------------------------------

DISCIPLINE_AGENT_CATALOG: dict[Discipline, list[WorkspaceAgent]] = {
    Discipline.IT_OPS: [
        _agent("sql_assistant", "SQL Assistant", "Writes & explains approved read-only queries", "llm-gateway", True),
        _agent("customer_response", "Customer Response Assistant", "Drafts customer-impact comms for an incident", "content-engine", True),
        _agent("meeting_summarizer", "Meeting Summarizer", "Summarises a bridge call into actions & owners", "llm-gateway", True),
        _agent("policy_advisor", "Policy Advisor", "Answers 'what does our policy say' from the KB", "llm-gateway", True),
        _agent("log_analyzer", "Log Analyzer", "Finds the signal in noisy logs", "llm-gateway", True),
    ],
    Discipline.MARKETING: [
        _agent("seo_specialist", "SEO Specialist", "Plans keywords & optimises content to rank", "llm-gateway", True),
        _agent("ad_copywriter", "Ad Copywriter", "Writes paid-ad variations to test", "content-engine", True),
        _agent("email_automator", "Email Automator", "Designs lifecycle email sequences", "content-engine", True),
        _agent("brand_strategist", "Brand Strategist", "Sharpens positioning & narrative", "llm-gateway", True),
        _agent("community_manager", "Community Manager", "Plans community & engagement moves", "llm-gateway", True),
    ],
    Discipline.SALES: [
        _agent("lead_enricher", "Lead Enricher", "Enriches leads with firmographic detail", "smart-scraper", True),
        _agent("battlecard_maker", "Battlecard Maker", "Builds competitor battlecards", "llm-gateway", True),
        _agent("proposal_writer", "Proposal Writer", "Drafts tailored proposals fast", "content-engine", True),
        _agent("forecast_analyst", "Forecast Analyst", "Reads the pipeline and forecasts", "llm-gateway", True),
    ],
    Discipline.ENGINEERING: [
        _agent("security_reviewer", "Security Reviewer", "Scans your change for security issues", "llm-gateway", True),
        _agent("perf_profiler", "Performance Profiler", "Flags performance hotspots", "llm-gateway", True),
        _agent("devops_helper", "DevOps Helper", "Drafts CI/CD & deploy config", "llm-gateway", True),
        _agent("refactor_assistant", "Refactor Assistant", "Suggests safe refactors", "llm-gateway", True),
        _agent("api_designer", "API Designer", "Designs clean, consistent APIs", "llm-gateway", True),
    ],
    Discipline.DESIGN: [
        _agent("accessibility_checker", "Accessibility Checker", "Reviews designs for a11y", "llm-gateway", True),
        _agent("illustration_briefer", "Illustration Briefer", "Briefs & directs visual assets", "content-engine", True),
        _agent("usability_tester", "Usability Tester", "Plans quick usability tests", "llm-gateway", True),
    ],
    Discipline.PRODUCT: [
        _agent("competitor_teardown", "Competitor Teardown", "Tears down competing products", "smart-scraper", True),
        _agent("pricing_analyst", "Pricing Analyst", "Models pricing & packaging", "llm-gateway", True),
        _agent("story_writer", "User-Story Writer", "Turns needs into crisp stories", "content-engine", True),
    ],
    Discipline.OPERATIONS: [
        _agent("automation_scout", "Automation Scout", "Finds tasks to automate", "llm-gateway", True),
        _agent("vendor_evaluator", "Vendor Evaluator", "Compares vendors & tools", "smart-scraper", True),
        _agent("sla_drafter", "SLA Drafter", "Drafts SLAs & runbooks", "content-engine", True),
    ],
    Discipline.RESEARCH: [
        _agent("survey_designer", "Survey Designer", "Designs unbiased surveys", "llm-gateway", True),
        _agent("competitive_scan", "Competitive Scanner", "Scans the competitive landscape", "smart-scraper", True),
        _agent("stat_reviewer", "Stat Reviewer", "Sanity-checks claims & numbers", "llm-gateway", True),
    ],
    Discipline.DATA: [
        _agent("viz_builder", "Viz Builder", "Recommends the right chart", "llm-gateway", True),
        _agent("anomaly_watcher", "Anomaly Watcher", "Spots anomalies in metrics", "llm-gateway", True),
        _agent("ab_test_designer", "A/B Test Designer", "Designs sound experiments", "llm-gateway", True),
    ],
    Discipline.FINANCE: [
        _agent("scenario_planner", "Scenario Planner", "Models best/base/worst cases", "llm-gateway", True),
        _agent("grant_finder", "Grant & Funding Finder", "Finds relevant funding", "smart-scraper", True),
        _agent("burn_analyst", "Burn Analyst", "Tracks burn & runway", "llm-gateway", True),
    ],
    Discipline.LEGAL: [
        _agent("policy_drafter", "Policy Drafter", "Drafts privacy & policy docs", "content-engine", True),
        _agent("reg_scanner", "Regulation Scanner", "Scans applicable regulations", "smart-scraper", True),
        _agent("risk_flagger", "Risk Flagger", "Flags legal risk (not advice)", "llm-gateway", True),
    ],
    Discipline.SUPPORT: [
        _agent("sentiment_analyst", "Sentiment Analyst", "Reads customer sentiment", "llm-gateway", True),
        _agent("macro_optimiser", "Macro Optimiser", "Improves reusable replies", "content-engine", True),
        _agent("faq_builder", "FAQ Builder", "Turns tickets into FAQs", "content-engine", True),
    ],
    Discipline.CONTENT: [
        _agent("seo_editor", "SEO Editor", "Optimises content to rank", "llm-gateway", True),
        _agent("repurposer", "Repurposer", "Turns one piece into many formats", "content-engine", True),
        _agent("fact_checker", "Fact Checker", "Verifies claims before publish", "llm-gateway", True),
    ],
}


def agent_catalog_for(discipline: Discipline) -> list[WorkspaceAgent]:
    """Additional role-relevant agents a contributor may request for this discipline."""
    return [a.model_copy(deep=True) for a in DISCIPLINE_AGENT_CATALOG.get(discipline, [])]


def find_agent(discipline: Discipline, agent_key: str) -> Optional[WorkspaceAgent]:
    """Look up an agent by key across a discipline's BASE kit + requestable catalog."""
    for a in DISCIPLINE_KITS.get(discipline, {}).get("agents", []):
        if a.key == agent_key:
            return a.model_copy(deep=True)
    for a in DISCIPLINE_AGENT_CATALOG.get(discipline, []):
        if a.key == agent_key:
            return a.model_copy(deep=True)
    return None


def resolve_status(tool: WorkspaceTool) -> str:
    """Runtime connect-status for a tool (thin layer over the pure registry)."""
    if tool.kind == "builtin":
        return "connected"
    if tool.kind == "env":
        return "connected" if os.environ.get(tool.env_var or "", "").strip() else "needs_setup"
    return "available"  # external — the contributor links it themselves


def resolved_blueprint(discipline: Discipline, vertical: Vertical) -> WorkspaceBlueprint:
    """Blueprint with tool statuses resolved against the current environment."""
    bp = blueprint_for(discipline, vertical)
    for t in bp.tools:
        t.status = resolve_status(t)
    return bp
