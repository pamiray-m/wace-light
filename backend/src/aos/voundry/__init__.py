"""
Voundry — the AOS-1 Venture Foundry module (Q4 2026 Venture Module).

Voundry is a *governed, human-contributor* venture-creation layer. Raw ideas are
submitted, AI-screened (reusing the deterministic VE engine as a stateless
scoring/governance brain), curated into candidates, activated into governed
Venture Units behind a human-approval gate, decomposed into milestones and work
units, executed by contributors who submit evidence-backed deliverables, scored
through a transparent contribution-credit formula, and recorded in an append-only
ledger with full audit + lineage.

This package is the first **vertical-slice MVP**: one governed venture lifecycle,
end-to-end, persisted and audited. It deliberately reuses AOS-1's existing
governance substrate (GEL human-approval gate, lineage enforcement, kill switch)
rather than re-implementing it.

NOT a securities/crowdfunding/token platform. AI proposes; humans approve every
material decision. Contribution credits are non-transferable recognition units —
never equity, securities, wages, or guaranteed returns.
"""
