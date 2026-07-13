"""
Voundry workspace agent runtime — how a contributor actually USES their agents.

A contributor briefs an agent in plain words; the agent returns a draft the
contributor owns, edits, and decides what to do with. Agents never take
autonomous action — they assist. Every run is:

- GOVERNED: it goes through the live AOS LLM gateway, which applies the SAIb
  guard (PII/secrets never leave) and the model-cost router. When no LLM is
  reachable the run returns a deterministic starter scaffold instead of failing.
- SCOPED: only agents on the contributor's roster for that role-assignment
  (the role's default allocated agents + any they've requested) can be run.
- RECEIPTED: every run writes a WORM audit event and is retained, so it shows
  up on the transparency feed like everything else.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.aos.voundry.contracts import AgentRun, ContributorProfile, VentureUnit, WorkUnit
from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo
from src.aos.voundry.workspace_blueprint import (
    DISCIPLINE_KITS,
    Vertical,
    derive_vertical,
    discipline_from_role_type,
    find_agent,
)

_MAX_BRIEF = 2000
_MAX_OUTPUT = 8000


class AgentRunError(Exception):
    pass


def _default_generate(*, system: str, prompt: str) -> tuple[str, str]:
    """Return (output, mode). Routes through the tenant's BYOK LLM key when set
    (their Anthropic account is billed), else the shared platform key if the
    tenant allows it; falls back to a deterministic scaffold when no LLM runs."""
    # Resolve the tenant BYOK posture (single-org). Any failure → platform default.
    override: Optional[str] = None
    allow_bridge = True
    try:
        from src.aos.voundry.byok import allow_platform_fallback, tenant_api_key
        override = tenant_api_key()
        if override is None:
            if not allow_platform_fallback():
                # No tenant key and platform fallback disabled → AI is off until set.
                return ("Configure your organization's LLM key in the Command Center "
                        "to enable the AI assistant.", "byok_required")
        else:
            # Tenant key present: only touch the platform bridge if fallback is allowed.
            allow_bridge = allow_platform_fallback()
    except Exception:  # noqa: BLE001 — BYOK unavailable → platform default behavior
        override, allow_bridge = None, True
    try:
        from src.llm.gateway import LLMUnavailableError, llm_gateway
        try:
            resp = llm_gateway.complete(prompt, system=system, task_hint="voundry_agent",
                                        api_key_override=override, allow_bridge_fallback=allow_bridge)
            text = (resp.text or "").strip()
            if text:
                return text[:_MAX_OUTPUT], "ai"
        except LLMUnavailableError:
            pass
    except Exception:  # noqa: BLE001 — any gateway import/runtime issue → scaffold
        pass
    return "", "scaffold"


def _scaffold(agent_name: str, capability: str, brief: str) -> str:
    """A genuinely useful, deterministic starting draft when the AI gateway
    isn't configured — clearly labelled so nobody mistakes it for a full draft."""
    header = (
        f"[Starter draft from {agent_name} — connect the AI gateway "
        f"(ANTHROPIC_API_KEY) for a full AI draft]\n\nYour brief: {brief}\n"
    )
    plans = {
        "content-engine": [
            "Hook — one line that earns the read",
            "Core message — the single point to land",
            "Proof — evidence, example, or number",
            "Call to action — the one next step",
        ],
        "smart-scraper": [
            "Define exactly what to find and why",
            "List the sources/segments to search",
            "Capture 5–10 candidates with the key fields",
            "Note assumptions and gaps to verify",
        ],
        "llm-gateway": [
            "Restate the goal in one sentence",
            "Options / approach with trade-offs",
            "Recommendation and why",
            "Next actions you can take now",
        ],
        "assistant": [
            "Clarify the ask", "Draft the response", "Review against the goal",
        ],
    }
    steps = plans.get(capability, plans["assistant"])
    body = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
    return header + "\nSuggested structure:\n" + body


def _split_citations(text: str) -> tuple[str, list[dict]]:
    """Split an analyze reply into (prose, [grounding citations]).

    The agent is asked to append `CITATIONS:` + a JSON array grounding its claims
    in numbered source lines. Parsing is lenient: if the block is missing or
    malformed, we return the full prose with no citations (never raise).
    """
    if not text or "CITATIONS:" not in text.upper():
        return (text or "", [])
    import json
    idx = text.upper().rindex("CITATIONS:")
    prose = text[:idx].rstrip()
    raw = text[idx + len("CITATIONS:"):].strip().strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return (prose or text, [])
    try:
        parsed = json.loads(raw[start:end + 1])
    except Exception:  # noqa: BLE001
        return (prose or text, [])
    out: list[dict] = []
    for c in parsed if isinstance(parsed, list) else []:
        if not isinstance(c, dict):
            continue
        claim = str(c.get("claim", "")).strip()[:280]
        if not claim:
            continue
        lines = [int(n) for n in c.get("lines", []) if isinstance(n, (int, float))][:10]
        conf = str(c.get("confidence", "")).strip().lower()
        if conf not in ("high", "medium", "low"):
            conf = "medium"
        out.append({"claim": claim, "lines": lines, "confidence": conf})
    return (prose or text, out[:5])


def _parse_investigation(text: str) -> tuple:
    """Lenient parse of an RCA reply into (hypothesis, [commands])."""
    if not text:
        return ("(No analysis available — the AI gateway is offline.)", [])
    if "COMMANDS:" not in text.upper():
        return (text.replace("HYPOTHESIS:", "").strip()[:_MAX_OUTPUT], [])
    idx = text.upper().index("COMMANDS:")
    hyp = text[:idx].replace("HYPOTHESIS:", "").replace("Hypothesis:", "").strip()
    cmds = []
    for line in text[idx + len("COMMANDS:"):].splitlines():
        line = line.strip().lstrip("$").strip().strip("`").lstrip("-•* ").strip()
        if line and not line.lower().startswith(("hypothesis", "note", "these ", "run ")):
            cmds.append(line[:200])
    return (hyp[:_MAX_OUTPUT] or "(see commands below)", cmds[:5])


class AgentRuntime:
    def __init__(self, repo=voundry_repo, audit=voundry_audit,
                 generate: Optional[Callable[..., tuple[str, str]]] = None) -> None:
        self._repo = repo
        self._audit = audit
        self._generate = generate or _default_generate

    def roster_keys(self, contributor_id: str, discipline_value: str) -> list[str]:
        """The agent keys a contributor may run for a discipline: role defaults
        + any they've requested."""
        from src.aos.voundry.workspace_blueprint import Discipline
        try:
            disc = Discipline(discipline_value)
        except ValueError:
            return []
        base = [a.key for a in DISCIPLINE_KITS.get(disc, {}).get("agents", [])]
        prof = self._repo.get_contributor(contributor_id)
        added = (prof or {}).get("added_agents", {}).get(disc.value, []) if prof else []
        return base + [k for k in added if k not in base]

    def run(self, *, contributor_id: str, work_unit_id: str, agent_key: str, brief: str) -> AgentRun:
        brief = (brief or "").strip()
        if not brief:
            raise AgentRunError("Give the agent a short brief of what you need.")
        brief = brief[:_MAX_BRIEF]

        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise AgentRunError("Work unit not found.")
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise AgentRunError("This isn't your assignment.")

        venture_d = self._repo.get_venture(wu.venture_unit_id)
        venture = VentureUnit(**venture_d) if venture_d else None
        discipline = discipline_from_role_type(wu.role_type)
        vertical = self._resolve_vertical(venture)

        if agent_key not in self.roster_keys(contributor_id, discipline.value):
            raise AgentRunError("That agent isn't on your workspace roster. Request it first.")
        agent = find_agent(discipline, agent_key)
        if agent is None:
            raise AgentRunError("Unknown agent.")

        venture_name = venture.name if venture else "this venture"
        system = (
            f"You are {agent.name}, an expert {discipline.value} assistant helping a human "
            f"contributor build a {vertical.value} venture called '{venture_name}' inside "
            f"Voundry (an AOS-1 venture foundry by mAIb Tech). You DRAFT and ASSIST; the human "
            f"owns, edits, and decides. Be concrete, concise, and ready-to-edit. "
            f"Do not fabricate facts, numbers, or sources — mark assumptions clearly."
        )
        prompt = f"Task: {agent.does}.\nContributor's brief: {brief}\n\nProduce the draft."

        output, mode = self._generate(system=system, prompt=prompt)
        if not output:
            output = _scaffold(agent.name, agent.powered_by, brief)
            mode = "scaffold"

        run = AgentRun(
            contributor_id=contributor_id, work_unit_id=work_unit_id,
            venture_unit_id=wu.venture_unit_id, agent_key=agent.key, agent_name=agent.name,
            capability=agent.powered_by, brief=brief, output=output[:_MAX_OUTPUT], mode=mode,
        )
        self._repo.save_agent_run(run)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="agent.run",
            resource_type="work_unit", resource_id=work_unit_id,
            detail=f"ran {agent.name} ({mode})",
            metadata={"agent_key": agent.key, "capability": agent.powered_by, "mode": mode},
        )
        return run

    def explain_terminal(self, *, contributor_id: str, work_unit_id: str, host: str,
                         command: str, output: str) -> dict:
        """An ops analyst reads a server command's output for the operator (governed)."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise AgentRunError("Work unit not found.")
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise AgentRunError("This isn't your assignment.")
        system = (
            "You are an expert Linux/UNIX operations analyst embedded in a governed ops console. "
            "A human operator ran a command on a production server and wants a concise, accurate read "
            "of the output. Explain what it means, flag anything abnormal or concerning, and suggest at "
            "most two safe, read-only next diagnostic commands. Do NOT invent values that aren't in the "
            "output. Be brief and concrete."
        )
        prompt = (f"Host: {host}\nCommand: {command}\n\nOutput:\n{(output or '')[:6000]}\n\n"
                  "Give a short read of what this shows, then up to 2 safe next diagnostic commands.")
        text, mode = self._generate(system=system, prompt=prompt)
        if not text:
            text = "(No analysis available — the AI gateway is offline.)"
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="terminal.explain",
            resource_type="work_unit", resource_id=work_unit_id, detail=f"{host}: {command}"[:200],
            metadata={"host": host, "mode": mode},
        )
        return {"analysis": text[:_MAX_OUTPUT], "mode": mode}

    def shift_report(self, *, contributor_id: str, work_unit_id: str, agent_key: str) -> dict:
        """An agent drafts an end-of-shift handoff from the desk's activity log."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise AgentRunError("Work unit not found.")
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise AgentRunError("This isn't your assignment.")
        discipline = discipline_from_role_type(wu.role_type)
        if agent_key not in self.roster_keys(contributor_id, discipline.value):
            raise AgentRunError("That agent isn't on your workspace roster. Request it first.")
        agent = find_agent(discipline, agent_key)
        if agent is None:
            raise AgentRunError("Unknown agent.")
        from src.aos.voundry.governance import voundry_audit
        events = voundry_audit.list_for_resource(work_unit_id, limit=60)
        activity = "\n".join(f"- [{(e.get('created_at') or '')[:16].replace('T', ' ')}] {e.get('action')}: {e.get('detail')}"
                             for e in events) or "(no recorded activity)"
        system = (
            f"You are {agent.name}. Write a concise end-of-shift handoff report for the next operator from the "
            f"desk's activity log. Use sections: Summary, What was done, Open items / follow-ups, and Watch next "
            f"shift. Do NOT invent events that aren't in the log. Be factual and brief."
        )
        text, mode = self._generate(system=system, prompt=f"Desk activity (most recent first):\n{activity[:6000]}\n\nWrite the shift report.")
        if not text:
            text = "(No report available — the AI gateway is offline.)"
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="agent.shift_report",
            resource_type="work_unit", resource_id=work_unit_id, detail=f"{agent.name} shift report ({len(events)} events)",
            metadata={"agent_key": agent_key, "events": len(events), "mode": mode},
        )
        return {"agent_name": agent.name, "report": text[:_MAX_OUTPUT], "mode": mode}

    def investigate(self, *, contributor_id: str, work_unit_id: str, agent_key: str, incident: str) -> dict:
        """RCA: turn an incident into a hypothesis + safe diagnostic commands."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise AgentRunError("Work unit not found.")
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise AgentRunError("This isn't your assignment.")
        discipline = discipline_from_role_type(wu.role_type)
        if agent_key not in self.roster_keys(contributor_id, discipline.value):
            raise AgentRunError("That agent isn't on your workspace roster. Request it first.")
        agent = find_agent(discipline, agent_key)
        if agent is None:
            raise AgentRunError("Unknown agent.")
        system = (
            f"You are {agent.name}, an incident RCA investigator. Given an incident, produce a likely-cause "
            f"hypothesis, then SAFE, READ-ONLY diagnostic shell commands to confirm it. Reply EXACTLY in this "
            f"format:\nHYPOTHESIS: <one short paragraph>\nCOMMANDS:\n<one shell command per line, no prose, at "
            f"most 5>. Do not invent hostnames or values not in the incident."
        )
        text, mode = self._generate(system=system, prompt=f"Incident:\n{(incident or '')[:4000]}\n\nInvestigate.")
        hypothesis, commands = _parse_investigation(text)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="agent.investigate",
            resource_type="work_unit", resource_id=work_unit_id, detail=f"{agent.name} investigated an incident",
            metadata={"agent_key": agent_key, "commands": len(commands), "mode": mode},
        )
        return {"agent_name": agent.name, "hypothesis": hypothesis, "commands": commands, "mode": mode}

    def analyze_data(self, *, contributor_id: str, work_unit_id: str, agent_key: str,
                     source: str, data: str) -> dict:
        """A desk agent reads live data pulled from a governed connector (the WACE thesis)."""
        w = self._repo.get_work_unit(work_unit_id)
        if w is None:
            raise AgentRunError("Work unit not found.")
        wu = WorkUnit(**w)
        if wu.assigned_to != contributor_id:
            raise AgentRunError("This isn't your assignment.")
        discipline = discipline_from_role_type(wu.role_type)
        if agent_key not in self.roster_keys(contributor_id, discipline.value):
            raise AgentRunError("That agent isn't on your workspace roster. Request it first.")
        agent = find_agent(discipline, agent_key)
        if agent is None:
            raise AgentRunError("Unknown agent.")
        system = (
            f"You are {agent.name}, an expert {discipline.value} assistant. A human operator is showing you "
            f"live data pulled from a governed connector. Read it and give a concise, accurate analysis: what "
            f"matters, anything abnormal or urgent, and recommended next steps. Do NOT invent values that aren't "
            f"in the data. Be brief and concrete; the human owns the decision.\n"
            f"GROUNDING: the data is presented as numbered lines. After your analysis, append a line that is "
            f"exactly 'CITATIONS:' followed by a compact JSON array (max 5) of "
            f'{{"claim": "<short claim>", "lines": [<source line numbers>], "confidence": "high|medium|low"}}. '
            f"Cite the line numbers that support each key claim; if the data does not support a claim, mark it "
            f"low confidence. Output nothing after the JSON array."
        )
        numbered = "\n".join(f"{i + 1}| {ln}" for i, ln in enumerate((data or "")[:6000].split("\n")))
        prompt = f"Source: {source}\n\nData (numbered lines):\n{numbered}\n\nAnalyze this for the operator."
        text, mode = self._generate(system=system, prompt=prompt)
        if not text:
            text = "(No analysis available — the AI gateway is offline.)"
        analysis, citations = _split_citations(text)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="agent.analyze",
            resource_type="work_unit", resource_id=work_unit_id,
            detail=f"{agent.name} analyzed {source}"[:200],
            metadata={"agent_key": agent_key, "source": source, "mode": mode, "citations": len(citations)},
        )
        return {"agent_name": agent.name, "analysis": analysis[:_MAX_OUTPUT], "mode": mode, "citations": citations}

    def list_runs(self, work_unit_id: str) -> list[dict]:
        rows = self._repo.list_agent_runs_for_work_unit(work_unit_id)
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    def _resolve_vertical(self, venture: Optional[VentureUnit]) -> Vertical:
        if venture is None:
            return Vertical.GENERIC
        stored = (venture.vertical or "").strip().lower()
        try:
            if stored and stored != "generic":
                return Vertical(stored)
        except ValueError:
            pass
        cand = self._repo.get_candidate(venture.candidate_id)
        if cand:
            idea = self._repo.get_idea(cand.get("idea_id", ""))
            if idea:
                from src.aos.voundry.contracts import Idea
                i = Idea(**idea)
                return derive_vertical(i.market, i.summary, i.business_model, venture.name)
        return Vertical.GENERIC


# Module-level singleton
agent_runtime = AgentRuntime()
