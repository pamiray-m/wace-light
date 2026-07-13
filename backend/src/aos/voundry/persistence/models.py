"""
SQLAlchemy ORM models for Voundry persistence.

One table per lifecycle entity. Each stores the full Pydantic model payload as a
JSON column plus indexed scalar columns for common lookups (id, foreign keys,
status). This mirrors the mission-pipeline persistence design
(src/aos/missions/persistence/models.py) and keeps deeply-nested models simple
while keeping joins-by-id fast.

The voundry_audit_events table is append-only (no UPDATE/DELETE paths in the
application) — it is the module's WORM audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.sqlite import JSON

from src.core.registry.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


class VoundryIdeaRecord(Base):
    __tablename__ = "voundry_ideas"

    id           = Column(String, primary_key=True)
    submitted_by = Column(String, nullable=False, index=True)
    status       = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundryScreeningRecord(Base):
    __tablename__ = "voundry_screening_reports"

    id         = Column(String, primary_key=True)
    idea_id    = Column(String, nullable=False, index=True)
    verdict    = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload    = Column(JSON, nullable=False)


class VoundryCandidateRecord(Base):
    __tablename__ = "voundry_candidates"

    id         = Column(String, primary_key=True)
    idea_id    = Column(String, nullable=False, index=True)
    status     = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload    = Column(JSON, nullable=False)


class VoundryVentureRecord(Base):
    __tablename__ = "voundry_ventures"

    id           = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    status       = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundryMilestoneRecord(Base):
    __tablename__ = "voundry_milestones"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    status          = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryWorkUnitRecord(Base):
    __tablename__ = "voundry_work_units"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    milestone_id    = Column(String, nullable=False, index=True)
    status          = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryApplicationRecord(Base):
    __tablename__ = "voundry_applications"

    id           = Column(String, primary_key=True)
    work_unit_id = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    status       = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundrySubmissionRecord(Base):
    __tablename__ = "voundry_submissions"

    id           = Column(String, primary_key=True)
    work_unit_id = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    status       = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundryReviewRecord(Base):
    __tablename__ = "voundry_reviews"

    id            = Column(String, primary_key=True)
    submission_id = Column(String, nullable=False, index=True)
    reviewer_type = Column(String, nullable=False, index=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload       = Column(JSON, nullable=False)


class VoundryContributionRecord(Base):
    __tablename__ = "voundry_contribution_records"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    work_unit_id    = Column(String, nullable=False, index=True)
    contributor_id  = Column(String, nullable=False, index=True)
    approval_status = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryDecisionLogRecord(Base):
    __tablename__ = "voundry_decision_log"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    decision_type   = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryRiskRecord(Base):
    __tablename__ = "voundry_risk_register"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    severity        = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryAccountRecord(Base):
    """Standalone Voundry-app login accounts (founders / contributors / investors)."""
    __tablename__ = "voundry_accounts"

    account_id = Column(String, primary_key=True)
    email      = Column(String, nullable=False, unique=True, index=True)
    role       = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload    = Column(JSON, nullable=False)


class VoundryVerificationRecord(Base):
    __tablename__ = "voundry_verifications"

    id             = Column(String, primary_key=True)
    contributor_id = Column(String, nullable=False, index=True)
    status         = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryContributorRecord(Base):
    __tablename__ = "voundry_contributors"

    contributor_id = Column(String, primary_key=True)
    tier           = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryTrustPageRecord(Base):
    """Admin overrides for Trust Center pages (canonical content is in code)."""
    __tablename__ = "voundry_trust_pages"

    slug       = Column(String, primary_key=True)
    title      = Column(String, nullable=False)
    body       = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class VoundryReportRecord(Base):
    __tablename__ = "voundry_reports"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    published       = Column(String, nullable=False, index=True)  # "true"/"false"
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryIPRecord(Base):
    __tablename__ = "voundry_ip_registry"

    id              = Column(String, primary_key=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    ip_mode         = Column(String, nullable=False, index=True)
    status          = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryWorkspaceMessageRecord(Base):
    __tablename__ = "voundry_workspace_messages"

    id           = Column(String, primary_key=True)
    work_unit_id = Column(String, nullable=False, index=True)
    venture_unit_id = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundryVoteRecord(Base):
    __tablename__ = "voundry_votes"

    id           = Column(String, primary_key=True)
    candidate_id = Column(String, nullable=False, index=True)
    voter_id     = Column(String, nullable=False, index=True)
    audience     = Column(String, nullable=False, index=True)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundryDisputeRecord(Base):
    __tablename__ = "voundry_disputes"

    id                     = Column(String, primary_key=True)
    contribution_record_id = Column(String, nullable=False, index=True)
    venture_unit_id        = Column(String, nullable=False, index=True)
    status                 = Column(String, nullable=False, index=True)
    created_at             = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload                = Column(JSON, nullable=False)


class VoundryInvestorPledgeRecord(Base):
    """Non-binding investor signals (watch / pledge-interest / sponsor / diligence)."""
    __tablename__ = "voundry_investor_pledges"

    id              = Column(String, primary_key=True)
    investor_id     = Column(String, nullable=False, index=True)
    venture_unit_id = Column(String, nullable=True, index=True)
    pledge_type     = Column(String, nullable=False, index=True)
    status          = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryGelApprovalRecord(Base):
    """
    Durable GEL approval tasks for Voundry (activation + high-value credit).

    Backs PersistentApprovalTaskStore so human approvals survive process
    restarts — the in-memory GEL store would otherwise lose the very approvals
    that gated activation/credit decisions, breaking the audit/trust guarantee.
    """
    __tablename__ = "voundry_gel_approvals"

    task_id     = Column(String, primary_key=True)
    contract_id = Column(String, nullable=False, index=True)
    status      = Column(String, nullable=False, index=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload     = Column(JSON, nullable=False)


class VoundryAuditRecord(Base):
    """Append-only WORM audit trail for Voundry. No UPDATE/DELETE paths."""
    __tablename__ = "voundry_audit_events"

    id            = Column(String, primary_key=True, default=_uid)
    actor_id      = Column(String, nullable=False, index=True)
    action        = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, index=True)
    resource_id   = Column(String, nullable=False, index=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload       = Column(JSON, nullable=False)


class VoundryJudgmentTaskRecord(Base):
    """System-spawned requests for human judgment on gated events."""
    __tablename__ = "voundry_judgment_tasks"

    id              = Column(String, primary_key=True)
    judgment_type   = Column(String, nullable=False, index=True)
    subject_id      = Column(String, nullable=False, index=True)
    venture_unit_id = Column(String, nullable=True, index=True)
    status          = Column(String, nullable=False, index=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload         = Column(JSON, nullable=False)


class VoundryJudgmentCreditRecord(Base):
    """Judgment-labor credit ledger (separate from the deliverable ledger)."""
    __tablename__ = "voundry_judgment_records"

    id               = Column(String, primary_key=True)
    judgment_task_id = Column(String, nullable=False, index=True)
    judge_id         = Column(String, nullable=False, index=True)
    vesting_status   = Column(String, nullable=False, index=True)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload          = Column(JSON, nullable=False)


class VoundryLegalDocumentRecord(Base):
    """Versioned legal documents (platform pack + venture-scoped NDAs)."""
    __tablename__ = "voundry_legal_documents"

    id           = Column(String, primary_key=True)
    kind         = Column(String, nullable=False, index=True)
    scope        = Column(String, nullable=False, index=True)
    candidate_id = Column(String, nullable=True, index=True)
    active       = Column(String, nullable=False, index=True)  # "true"/"false"
    version      = Column(String, nullable=False)
    created_at   = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload      = Column(JSON, nullable=False)


class VoundrySignatureRecord(Base):
    """Insert-only click-wrap signature receipts. WORM: no UPDATE/DELETE paths."""
    __tablename__ = "voundry_signature_records"

    id          = Column(String, primary_key=True)
    account_id  = Column(String, nullable=False, index=True)
    document_id = Column(String, nullable=False, index=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload     = Column(JSON, nullable=False)


class VoundryAgentRunRecord(Base):
    """A contributor's invocation of a workspace AI agent (insert-only log)."""
    __tablename__ = "voundry_agent_runs"

    id             = Column(String, primary_key=True)
    contributor_id = Column(String, nullable=False, index=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    agent_key      = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryWorkspaceFileRecord(Base):
    """A saved working file in a contributor's workspace (editable, deletable)."""
    __tablename__ = "voundry_workspace_files"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryInterviewRecord(Base):
    """An adaptive intake interview session (branching Q&A + scored result)."""
    __tablename__ = "voundry_interview_sessions"

    id             = Column(String, primary_key=True)
    contributor_id = Column(String, nullable=False, index=True)
    status         = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryConnectedToolRecord(Base):
    """An external tool connected to a workspace via a governed connector."""
    __tablename__ = "voundry_connected_tools"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    connector_key  = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryWriteRequestRecord(Base):
    """A governed, human-approved write-back to an external system."""
    __tablename__ = "voundry_write_requests"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    status         = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryBridgeRecord(Base):
    """A customer-network connector bridge paired to a desk."""
    __tablename__ = "voundry_bridges"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundrySavedQueryRecord(Base):
    """A saved read-only SQL query for a desk."""
    __tablename__ = "voundry_saved_queries"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryTerminalRunbookRecord(Base):
    """A saved diagnostic command set for the governed terminal."""
    __tablename__ = "voundry_terminal_runbooks"

    id             = Column(String, primary_key=True)
    work_unit_id   = Column(String, nullable=False, index=True)
    contributor_id = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)


class VoundryOrgPolicyRecord(Base):
    """The org-wide WACE governance policy (single row, id='org')."""
    __tablename__ = "voundry_org_policy"

    id         = Column(String, primary_key=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload    = Column(JSON, nullable=False)


class VoundryBridgeJobRecord(Base):
    """A connector call routed to a bridge for local execution."""
    __tablename__ = "voundry_bridge_jobs"

    id             = Column(String, primary_key=True)
    bridge_id      = Column(String, nullable=False, index=True)
    status         = Column(String, nullable=False, index=True)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)
    payload        = Column(JSON, nullable=False)
