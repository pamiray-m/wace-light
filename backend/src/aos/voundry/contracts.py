"""
Voundry domain contracts — Pydantic v2 models, status enums, and state machines.

Pure data + validation layer for the vertical-slice lifecycle:

  Idea → ScreeningReport → VentureCandidate → VentureUnit
       → Milestone → WorkUnit → WorkUnitApplication
       → ContributionSubmission → Review → ContributionRecord

plus the governance side-records DecisionLogEntry and RiskRegisterItem.

Design notes
------------
- Models are mutable BaseModels (status fields advance through their state
  machines); the service mutates via model_copy/assignment and persists the full
  payload as JSON. Validity of every status transition is enforced by the
  VALID_*_TRANSITIONS tables + validate_*_transition() helpers.
- ContributionRecord exposes EVERY credit component (no invisible scoring) and
  deliberately has NO transfer field or method — credits are non-transferable.
- No imports from api.*, dag.*, or heavy runtime — importable anywhere.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IdeaStatus(str, Enum):
    SUBMITTED           = "submitted"
    AI_SCREENED         = "ai_screened"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED            = "rejected"
    WATCH               = "watch"
    CURATED             = "curated"
    ARCHIVED            = "archived"


class CandidateStatus(str, Enum):
    VOTING           = "voting"
    NOT_SELECTED     = "not_selected"
    ACTIVATION_READY = "activation_ready"
    ACTIVATED        = "activated"
    ARCHIVED         = "archived"


class VentureUnitStatus(str, Enum):
    ACTIVE    = "active"
    PAUSED    = "paused"
    PIVOTING  = "pivoting"
    KILLED    = "killed"
    GRADUATED = "graduated"
    ARCHIVED  = "archived"


class GraduationOutcome(str, Enum):
    INTERNAL_AOS_PRODUCT = "internal_aos_product"
    SPINOUT_COMPANY      = "spinout_company"
    LICENSED_VENTURE     = "licensed_venture"
    PARTNER_VENTURE      = "partner_venture"
    ARCHIVED             = "archived"


class MilestoneStatus(str, Enum):
    DRAFT        = "draft"
    ACTIVE       = "active"
    UNDER_REVIEW = "under_review"
    ACHIEVED     = "achieved"
    FAILED       = "failed"
    PAUSED       = "paused"
    CANCELLED    = "cancelled"


class WorkUnitStatus(str, Enum):
    DRAFT             = "draft"
    OPEN              = "open"
    ASSIGNED          = "assigned"
    SUBMITTED         = "submitted"
    UNDER_AI_REVIEW   = "under_ai_review"
    UNDER_HUMAN_REVIEW = "under_human_review"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    DISPUTED          = "disputed"
    CLOSED            = "closed"


class ApplicationStatus(str, Enum):
    SUBMITTED   = "submitted"
    SHORTLISTED = "shortlisted"
    ACCEPTED    = "accepted"
    REJECTED    = "rejected"
    WITHDRAWN   = "withdrawn"


class SubmissionStatus(str, Enum):
    SUBMITTED         = "submitted"
    UNDER_REVIEW      = "under_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    DISPUTED          = "disputed"


class ReviewerType(str, Enum):
    AI                = "ai"
    PEER              = "peer"
    SENIOR_CONTRIBUTOR = "senior_contributor"
    HUMAN_GOVERNOR    = "human_governor"
    ADMIN             = "admin"


class RiskSeverity(str, Enum):
    LOW      = "low"
    MEDIUM   = "medium"
    HIGH     = "high"
    CRITICAL = "critical"


class CreditApprovalStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    ADJUSTED = "adjusted"


class VoteAudience(str, Enum):
    CONTRIBUTOR = "contributor"
    INVESTOR    = "investor"
    EXPERT      = "expert"


class VoteType(str, Enum):
    SUPPORT        = "support"
    INTEREST       = "interest"
    EXPERT_SUPPORT = "expert_support"
    CONCERN        = "concern"
    REJECT_SIGNAL  = "reject_signal"


class DisputeStatus(str, Enum):
    OPEN         = "open"
    UNDER_REVIEW = "under_review"
    ACCEPTED     = "accepted"
    REJECTED     = "rejected"
    RESOLVED     = "resolved"
    ESCALATED    = "escalated"


class ContributorTier(str, Enum):
    """Domain-record tier (NOT an auth principal in the vertical slice)."""
    OBSERVER     = "observer"
    APPLICANT    = "applicant"
    VERIFIED     = "verified"
    SENIOR       = "senior"
    VENTURE_LEAD = "venture_lead"
    AOS_OPERATOR = "aos_operator"


class PledgeType(str, Enum):
    WATCH             = "watch"
    PLEDGE_INTEREST   = "pledge_interest"
    SPONSOR_BOUNTY    = "sponsor_bounty"
    SPONSOR_MILESTONE = "sponsor_milestone"
    REQUEST_DILIGENCE = "request_diligence"


class PledgeStatus(str, Enum):
    INTEREST                   = "interest"
    PLEDGED                    = "pledged"
    SPONSORED_BOUNTY_INTENT    = "sponsored_bounty_intent"
    SPONSORED_MILESTONE_INTENT = "sponsored_milestone_intent"
    DILIGENCE_REQUESTED        = "diligence_requested"
    WITHDRAWN                  = "withdrawn"


class InvestorStatus(str, Enum):
    """Domain-record investor tier (NOT an auth principal in the slice)."""
    OBSERVER          = "observer"
    INVESTOR_ACCESS   = "investor_access"
    PRO_INVESTOR      = "pro_investor"
    SPONSOR           = "sponsor"
    STRATEGIC_PARTNER = "strategic_partner"


class VerificationStatus(str, Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationRequest(BaseModel):
    """A contributor's request to be vetted Applicant → Verified.

    Carries every credential the applicant offers — portfolio, LinkedIn,
    an imported CV (extracted text), and any other supporting links — plus
    a deterministic pre-approval assessment computed at submission so the
    reviewing human starts from evidence, not a blank page."""
    id:            str = Field(default_factory=_uid)
    contributor_id: str
    portfolio_url: str = ""
    linkedin_url:  str = ""
    credentials:   list[str] = Field(default_factory=list)   # certs, sites, repos…
    cv_filename:   str = ""
    cv_text:       str = ""                                   # extracted, truncated
    note:          str = ""
    assessment:    Optional[dict[str, Any]] = None            # deterministic pre-review
    status:        VerificationStatus = VerificationStatus.PENDING
    reviewed_by:   Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class ContributorProfile(BaseModel):
    """A contributor's domain profile + tier (NOT an auth principal in the slice)."""
    id:            str = Field(default_factory=_uid)
    contributor_id: str          # stable handle (unique)
    display_name:  str = ""
    tier:          ContributorTier = ContributorTier.APPLICANT
    skills:        list[str] = Field(default_factory=list)
    credits_total: int = 0
    # Grants the right to approve/reject governed write-backs at the GEL gate
    # (the "shift supervisor" capability). Enterprises grant this only to leads,
    # never to the ICs doing the work → two-key separation holds by policy.
    can_govern:    bool = False
    # Extra agents the contributor has requested, keyed by discipline value →
    # [agent_key]. Layered on top of a role's default allocated agents.
    added_agents:  dict[str, list[str]] = Field(default_factory=dict)
    # Result of the most recent adaptive intake interview (dimension scores +
    # composite + summary). Shown to reviewers and to the applicant themselves.
    interview_result: Optional[dict[str, Any]] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class InterviewTurn(BaseModel):
    """One question/answer exchange in an adaptive intake interview."""
    index:    int
    question: str
    answer:   str = ""


class InterviewStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"


class InterviewSession(BaseModel):
    """An adaptive, branching intake interview. Questions are generated turn by
    turn from the role + the running transcript, so no two runs are the same.
    Governed (LLM gateway + SAIb guard) and WORM-receipted like every AOS run."""
    id:              str = Field(default_factory=_uid)
    contributor_id:  str
    discipline:      str = "generic"
    focus:           str = ""                      # optional target role / area
    skills:          list[str] = Field(default_factory=list)
    turns:           list[InterviewTurn] = Field(default_factory=list)
    max_turns:       int = 5
    status:          InterviewStatus = InterviewStatus.IN_PROGRESS
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    composite:       float = 0.0
    summary:         str = ""
    mode:            str = "ai"                     # "ai" | "scaffold" (offline fallback)
    created_at:      datetime = Field(default_factory=_now)
    updated_at:      datetime = Field(default_factory=_now)


class AgentRun(BaseModel):
    """A single invocation of a workspace AI agent by a contributor.

    Agents draft; the human owns and edits the output and decides what to do
    with it. Every run is receipted (WORM audit) and surfaces on the feed."""
    id:            str = Field(default_factory=_uid)
    contributor_id: str
    work_unit_id:  str
    venture_unit_id: str = ""
    agent_key:     str
    agent_name:    str
    capability:    str           # content-engine | smart-scraper | llm-gateway | assistant
    brief:         str
    output:        str = ""
    mode:          str = "ai"    # "ai" (LLM produced) | "scaffold" (offline starter)
    created_at:    datetime = Field(default_factory=_now)


class ConnectedTool(BaseModel):
    """An external tool a contributor has connected to a workspace via a
    governed connector. Read-only in this release; every use is receipted.

    OAuth connectors (e.g. Microsoft 365 / Outlook via Graph) start life with
    auth_status='pending' and an authorize URL; once the contributor completes
    the provider consent the token lands in `config` and auth_status='connected'.
    """
    id:             str = Field(default_factory=_uid)
    work_unit_id:   str
    contributor_id: str
    connector_key:  str
    label:          str
    scope:          str = "read"
    status:         str = "connected"
    provider:       str = ""                     # "" (local) | "microsoft"
    auth_status:    str = "connected"            # connected | pending
    config:         dict[str, Any] = Field(default_factory=dict)   # holds oauth token for provider connectors
    created_at:     datetime = Field(default_factory=_now)


class SavedQuery(BaseModel):
    """An operator's saved read-only SQL query for a desk."""
    id:             str = Field(default_factory=_uid)
    work_unit_id:   str
    contributor_id: str
    name:           str
    sql:            str
    created_at:     datetime = Field(default_factory=_now)


class TerminalRunbook(BaseModel):
    """An operator's saved diagnostic command set for the governed terminal."""
    id:             str = Field(default_factory=_uid)
    work_unit_id:   str
    contributor_id: str
    name:           str
    commands:       list[str] = Field(default_factory=list)
    created_at:     datetime = Field(default_factory=_now)


class BridgeJobStatus(str, Enum):
    PENDING = "pending"     # queued for the bridge to pick up
    RUNNING = "running"     # claimed by the bridge
    DONE    = "done"
    FAILED  = "failed"


class ConnectorBridge(BaseModel):
    """A customer-network agent that WACE reaches internal systems THROUGH.
    The bridge dials home (outbound only) and executes jobs locally, so
    credentials + data never leave the customer's network. WACE stores only a
    hash of the pairing secret and a list of the connectors the bridge serves."""
    id:             str = Field(default_factory=_uid)
    work_unit_id:   str          # the desk this bridge serves
    contributor_id: str          # who paired it
    name:           str = "On-prem bridge"
    token_hash:     str = ""      # sha256 of the pairing secret — never the secret itself
    capabilities:   list[str] = Field(default_factory=list)   # connector_keys the bridge can serve
    # Optional operator allowlist of "connector:action" the bridge may run. Empty
    # = allow anything it's capable of. Lets a desk pin a bridge to read-only ops.
    allowed_actions: list[str] = Field(default_factory=list)
    status:         str = "unpaired"   # unpaired | online | offline (derived from last_seen)
    last_seen:      Optional[datetime] = None
    # Short one-time pairing code → the agent claims it for the token (self-pair).
    # The plaintext secret is held transiently only until claimed/expired.
    pair_code:      str = ""
    pair_secret:    str = ""
    pair_expires:   Optional[datetime] = None
    created_at:     datetime = Field(default_factory=_now)


class BridgeJob(BaseModel):
    """One connector call routed to a bridge for local execution."""
    id:            str = Field(default_factory=_uid)
    bridge_id:     str
    connector_key: str
    action:        str
    params:        dict[str, Any] = Field(default_factory=dict)
    spec:          Optional[dict[str, Any]] = None   # for no-code custom connectors
    status:        BridgeJobStatus = BridgeJobStatus.PENDING
    result:        Optional[dict[str, Any]] = None
    error:         str = ""
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    Optional[datetime] = None


class WriteRequestStatus(str, Enum):
    PENDING  = "pending"     # awaiting human approval at the GEL gate
    EXECUTED = "executed"    # approved + the external write ran
    REJECTED = "rejected"
    FAILED   = "failed"      # approved but the external write errored


class ConnectorWriteRequest(BaseModel):
    """A requested WRITE to an external system (e.g. set a Remedy incident's
    status). It never fires on request — it creates a GEL approval task and
    waits for a human governor. On approval the write executes and is receipted.
    This is the WACE Execution layer: governed, human-in-the-loop write-back."""
    id:             str = Field(default_factory=_uid)
    work_unit_id:   str
    contributor_id: str          # who requested it
    connected_id:   str
    connector_key:  str
    action:         str
    params:         dict[str, Any] = Field(default_factory=dict)
    summary:        str = ""      # human-readable "what will happen"
    status:         WriteRequestStatus = WriteRequestStatus.PENDING
    gel_task_id:    str = ""
    approver_id:    str = ""
    result:         Optional[dict[str, Any]] = None
    reject_reason:  str = ""
    requested_at:   datetime = Field(default_factory=_now)
    decided_at:     Optional[datetime] = None


class WorkspaceFile(BaseModel):
    """A saved working file in a contributor's workspace — usually an agent
    output the contributor kept, editable and reusable for further work."""
    id:               str = Field(default_factory=_uid)
    work_unit_id:     str
    contributor_id:   str
    name:             str
    kind:             str = "note"   # note | draft | research | spec | data
    content:          str = ""
    source_agent_key: str = ""
    source_agent_name: str = ""
    created_at:       datetime = Field(default_factory=_now)
    updated_at:       datetime = Field(default_factory=_now)


class IPMode(str, Enum):
    EVALUATION_LICENSE          = "evaluation_license"
    ASSIGNMENT_TO_VOUNDRY       = "assignment_to_voundry"
    ASSIGNMENT_TO_VENTURE       = "assignment_to_venture_entity"
    LICENSE_TO_VOUNDRY          = "license_to_voundry"
    OPEN_SOURCE                 = "open_source"
    CONTRACTOR_DELIVERABLE      = "contractor_deliverable"
    PENDING_REVIEW              = "pending_review"


# ---------------------------------------------------------------------------
# Domain error
# ---------------------------------------------------------------------------


class InvalidVoundryTransition(Exception):
    """Raised when a requested status transition is not permitted."""

    def __init__(self, entity: str, current: str, target: str, allowed: list[str]) -> None:
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid {entity} transition: '{current}' → '{target}'. "
            f"Allowed from '{current}': {allowed or ['none (terminal)']}."
        )


# ---------------------------------------------------------------------------
# State machines
# ---------------------------------------------------------------------------


VALID_IDEA_TRANSITIONS: dict[IdeaStatus, frozenset[IdeaStatus]] = {
    IdeaStatus.SUBMITTED:           frozenset({IdeaStatus.AI_SCREENED, IdeaStatus.REJECTED, IdeaStatus.ARCHIVED}),
    IdeaStatus.AI_SCREENED:         frozenset({IdeaStatus.NEEDS_CLARIFICATION, IdeaStatus.WATCH, IdeaStatus.CURATED, IdeaStatus.REJECTED, IdeaStatus.ARCHIVED}),
    IdeaStatus.NEEDS_CLARIFICATION: frozenset({IdeaStatus.AI_SCREENED, IdeaStatus.REJECTED, IdeaStatus.ARCHIVED}),
    IdeaStatus.WATCH:               frozenset({IdeaStatus.CURATED, IdeaStatus.REJECTED, IdeaStatus.ARCHIVED}),
    IdeaStatus.CURATED:             frozenset({IdeaStatus.ARCHIVED}),
    IdeaStatus.REJECTED:            frozenset(),
    IdeaStatus.ARCHIVED:            frozenset(),
}

VALID_CANDIDATE_TRANSITIONS: dict[CandidateStatus, frozenset[CandidateStatus]] = {
    CandidateStatus.VOTING:           frozenset({CandidateStatus.ACTIVATION_READY, CandidateStatus.NOT_SELECTED, CandidateStatus.ARCHIVED}),
    CandidateStatus.ACTIVATION_READY: frozenset({CandidateStatus.ACTIVATED, CandidateStatus.VOTING, CandidateStatus.ARCHIVED}),
    CandidateStatus.ACTIVATED:        frozenset({CandidateStatus.ARCHIVED}),
    CandidateStatus.NOT_SELECTED:     frozenset({CandidateStatus.ARCHIVED}),
    CandidateStatus.ARCHIVED:         frozenset(),
}

VALID_VENTURE_TRANSITIONS: dict[VentureUnitStatus, frozenset[VentureUnitStatus]] = {
    VentureUnitStatus.ACTIVE:    frozenset({VentureUnitStatus.PAUSED, VentureUnitStatus.PIVOTING, VentureUnitStatus.KILLED, VentureUnitStatus.GRADUATED, VentureUnitStatus.ARCHIVED}),
    VentureUnitStatus.PAUSED:    frozenset({VentureUnitStatus.ACTIVE, VentureUnitStatus.KILLED, VentureUnitStatus.ARCHIVED}),
    VentureUnitStatus.PIVOTING:  frozenset({VentureUnitStatus.ACTIVE, VentureUnitStatus.KILLED, VentureUnitStatus.ARCHIVED}),
    VentureUnitStatus.KILLED:    frozenset({VentureUnitStatus.ARCHIVED}),
    VentureUnitStatus.GRADUATED: frozenset({VentureUnitStatus.ARCHIVED}),
    VentureUnitStatus.ARCHIVED:  frozenset(),
}

VALID_WORK_UNIT_TRANSITIONS: dict[WorkUnitStatus, frozenset[WorkUnitStatus]] = {
    WorkUnitStatus.DRAFT:              frozenset({WorkUnitStatus.OPEN, WorkUnitStatus.CLOSED}),
    WorkUnitStatus.OPEN:               frozenset({WorkUnitStatus.ASSIGNED, WorkUnitStatus.CLOSED}),
    WorkUnitStatus.ASSIGNED:           frozenset({WorkUnitStatus.SUBMITTED, WorkUnitStatus.OPEN, WorkUnitStatus.CLOSED}),
    WorkUnitStatus.SUBMITTED:          frozenset({WorkUnitStatus.UNDER_AI_REVIEW, WorkUnitStatus.UNDER_HUMAN_REVIEW}),
    WorkUnitStatus.UNDER_AI_REVIEW:    frozenset({WorkUnitStatus.UNDER_HUMAN_REVIEW, WorkUnitStatus.APPROVED, WorkUnitStatus.REJECTED}),
    WorkUnitStatus.UNDER_HUMAN_REVIEW: frozenset({WorkUnitStatus.APPROVED, WorkUnitStatus.REJECTED, WorkUnitStatus.DISPUTED}),
    WorkUnitStatus.APPROVED:           frozenset({WorkUnitStatus.CLOSED, WorkUnitStatus.DISPUTED}),
    WorkUnitStatus.REJECTED:           frozenset({WorkUnitStatus.OPEN, WorkUnitStatus.DISPUTED, WorkUnitStatus.CLOSED}),
    WorkUnitStatus.DISPUTED:           frozenset({WorkUnitStatus.APPROVED, WorkUnitStatus.REJECTED, WorkUnitStatus.CLOSED}),
    WorkUnitStatus.CLOSED:             frozenset(),
}

VALID_SUBMISSION_TRANSITIONS: dict[SubmissionStatus, frozenset[SubmissionStatus]] = {
    SubmissionStatus.SUBMITTED:         frozenset({SubmissionStatus.UNDER_REVIEW, SubmissionStatus.CHANGES_REQUESTED, SubmissionStatus.APPROVED, SubmissionStatus.REJECTED}),
    SubmissionStatus.UNDER_REVIEW:      frozenset({SubmissionStatus.APPROVED, SubmissionStatus.REJECTED, SubmissionStatus.CHANGES_REQUESTED}),
    SubmissionStatus.CHANGES_REQUESTED: frozenset({SubmissionStatus.SUBMITTED, SubmissionStatus.REJECTED}),
    SubmissionStatus.APPROVED:          frozenset({SubmissionStatus.DISPUTED}),
    SubmissionStatus.REJECTED:          frozenset({SubmissionStatus.DISPUTED}),
    SubmissionStatus.DISPUTED:          frozenset({SubmissionStatus.APPROVED, SubmissionStatus.REJECTED}),
}


def _validate(entity: str, table: dict, current, target) -> None:
    allowed = table.get(current, frozenset())
    if target not in allowed:
        raise InvalidVoundryTransition(
            entity, getattr(current, "value", str(current)),
            getattr(target, "value", str(target)),
            sorted(getattr(s, "value", str(s)) for s in allowed),
        )


def validate_idea_transition(current: IdeaStatus, target: IdeaStatus) -> None:
    _validate("idea", VALID_IDEA_TRANSITIONS, current, target)


def validate_candidate_transition(current: CandidateStatus, target: CandidateStatus) -> None:
    _validate("candidate", VALID_CANDIDATE_TRANSITIONS, current, target)


def validate_venture_transition(current: VentureUnitStatus, target: VentureUnitStatus) -> None:
    _validate("venture_unit", VALID_VENTURE_TRANSITIONS, current, target)


def validate_work_unit_transition(current: WorkUnitStatus, target: WorkUnitStatus) -> None:
    _validate("work_unit", VALID_WORK_UNIT_TRANSITIONS, current, target)


def validate_submission_transition(current: SubmissionStatus, target: SubmissionStatus) -> None:
    _validate("submission", VALID_SUBMISSION_TRANSITIONS, current, target)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Idea(BaseModel):
    id:            str = Field(default_factory=_uid)
    title:         str
    summary:       str
    problem:       str = ""
    customer:      str = ""
    solution:      str = ""
    market:        str = ""
    business_model: str = ""
    required_skills: list[str] = Field(default_factory=list)
    submitted_by:  str
    ip_declaration: str = ""
    confidentiality: str = "public"
    consent_accepted: bool = False
    content_hash:  Optional[str] = None
    status:        IdeaStatus = IdeaStatus.SUBMITTED
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class ScreeningReport(BaseModel):
    id:            str = Field(default_factory=_uid)
    idea_id:       str
    component_scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = 0.0
    verdict:       str = "watch"          # reject | revise | watch | candidate | fast_track
    rationale:     str = ""
    recommended_next_action: str = ""
    ai_narrative:  Optional[str] = None   # best-effort LLM enrichment; may be None
    created_at:    datetime = Field(default_factory=_now)


class VentureCandidate(BaseModel):
    id:            str = Field(default_factory=_uid)
    idea_id:       str
    title:         str
    candidate_score:          float = 0.0
    ai_viability_score:       float = 0.0
    contributor_demand_score: float = 0.0
    investor_interest_score:  float = 0.0
    expert_admin_score:       float = 0.0
    aos_strategic_fit_score:  float = 0.0
    risk_level:    RiskSeverity = RiskSeverity.MEDIUM
    activation_threshold: float = 75.0
    contributor_interest_count: int = 0
    status:        CandidateStatus = CandidateStatus.VOTING
    curated_by:    Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class VentureUnit(BaseModel):
    id:            str = Field(default_factory=_uid)
    candidate_id:  str
    name:          str
    thesis:        str = ""
    vertical:      str = "generic"   # discipline × VERTICAL → role workspaces
    status:        VentureUnitStatus = VentureUnitStatus.ACTIVE
    human_governor_id: Optional[str] = None
    ai_venture_manager: str = "AI Venture Manager"
    current_milestone_id: Optional[str] = None
    ip_mode:       IPMode = IPMode.LICENSE_TO_VOUNDRY
    graduation_path: Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class Milestone(BaseModel):
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    name:          str
    description:   str = ""
    success_criteria: list[str] = Field(default_factory=list)
    target_date:   Optional[str] = None
    status:        MilestoneStatus = MilestoneStatus.DRAFT
    progress_percent: int = 0
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class WorkUnit(BaseModel):
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    milestone_id:  str
    title:         str
    description:   str = ""
    role_type:     str = "product"
    required_skills: list[str] = Field(default_factory=list)
    difficulty_score: int = 3      # 1..5
    impact_score:  int = 3         # 1..5
    scarcity_multiplier: float = 1.0
    estimated_credits_min: int = 0
    estimated_credits_max: int = 0
    cash_bounty_amount: float = 0.0
    currency:      str = "GBP"
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    deadline:      Optional[str] = None
    status:        WorkUnitStatus = WorkUnitStatus.DRAFT
    assigned_to:   Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class WorkUnitApplication(BaseModel):
    id:            str = Field(default_factory=_uid)
    work_unit_id:  str
    contributor_id: str
    application_text: str = ""
    relevant_experience: str = ""
    status:        ApplicationStatus = ApplicationStatus.SUBMITTED
    reviewed_by:   Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class ContributionSubmission(BaseModel):
    id:            str = Field(default_factory=_uid)
    work_unit_id:  str
    contributor_id: str
    submission_text: str = ""
    submission_url: Optional[str] = None
    evidence:      list[str] = Field(default_factory=list)
    self_assessment: Optional[str] = None
    status:        SubmissionStatus = SubmissionStatus.SUBMITTED
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class Review(BaseModel):
    id:            str = Field(default_factory=_uid)
    submission_id: str
    reviewer_type: ReviewerType
    reviewer_id:   str
    quality_score: float = 0.0
    completeness_score: float = 0.0
    strategic_value_score: float = 0.0
    timeliness_score: float = 0.0
    comments:      str = ""
    recommendation: str = ""     # accept | reject | revise
    created_at:    datetime = Field(default_factory=_now)


class ContributionRecord(BaseModel):
    """
    Transparent, evidence-backed record of approved contribution value.

    Exposes every credit component (no invisible scoring). Has NO transfer
    field or method: credits are non-transferable recognition units.
    """
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    work_unit_id:  str
    contributor_id: str
    submission_id: str
    base_points:   float
    quality_multiplier:   float
    impact_multiplier:    float
    timeliness_multiplier: float
    scarcity_multiplier:  float
    approval_confidence:  float
    final_credits: int
    approval_status: CreditApprovalStatus = CreditApprovalStatus.PENDING
    approved_by:   Optional[str] = None
    approved_at:   Optional[datetime] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class DecisionLogEntry(BaseModel):
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    decision_type: str
    decision:      str
    rationale:     str = ""
    made_by_type:  str = "human"   # ai | human
    made_by_id:    str = ""
    requires_human_approval: bool = False
    approval_status: str = "n/a"
    created_at:    datetime = Field(default_factory=_now)


class RiskRegisterItem(BaseModel):
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    risk_category: str
    description:   str = ""
    severity:      RiskSeverity = RiskSeverity.MEDIUM
    likelihood:    str = "possible"
    mitigation:    str = ""
    status:        str = "open"
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class InvestorPledge(BaseModel):
    """
    A non-binding investor signal — watch, pledge interest, sponsor intent, or
    diligence request. MVP investors do NOT buy securities here: `amount` is a
    declared *intent*, never a charge. There is deliberately no equity/share/
    token field and no transfer surface. Sponsor/pledge intents carry
    legal_review_required=True so nothing converts to capital without counsel.
    """
    id:            str = Field(default_factory=_uid)
    investor_id:   str
    venture_unit_id: Optional[str] = None
    candidate_id:  Optional[str] = None
    milestone_id:  Optional[str] = None
    pledge_type:   PledgeType
    amount:        Optional[float] = None     # declared intent only — never charged
    currency:      str = "GBP"
    conditions:    str = ""
    status:        PledgeStatus
    legal_review_required: bool = False
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class IPRegistryItem(BaseModel):
    """Tracks IP for a venture deliverable + its assigned IP mode (blueprint §15)."""
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    item_type:     str = "deliverable"
    title:         str
    description:   str = ""
    owner_or_contributor_id: str
    ip_mode:       IPMode = IPMode.PENDING_REVIEW
    linked_submission_id: Optional[str] = None
    linked_evidence: list[str] = Field(default_factory=list)
    status:        str = "open"        # open | resolved
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class WorkspaceKind(str, Enum):
    COMMENT     = "comment"
    AI_NOTE     = "ai_note"
    REVIEW_NOTE = "review_note"


class WorkspaceMessage(BaseModel):
    """A message in a work unit's collaboration thread."""
    id:            str = Field(default_factory=_uid)
    work_unit_id:  str
    venture_unit_id: str
    author_id:     str
    author_role:   str = "contributor"
    kind:          WorkspaceKind = WorkspaceKind.COMMENT
    body:          str
    created_at:    datetime = Field(default_factory=_now)


class Vote(BaseModel):
    """A weighted signal cast on a candidate. One per (candidate, voter)."""
    id:           str = Field(default_factory=_uid)
    candidate_id: str
    voter_id:     str
    audience:     VoteAudience
    vote_type:    VoteType
    weight:       float = 1.0
    pledged_hours: int = 0     # skin-in-the-game: hours the voter pledges to contribute
    rationale:    str = ""
    created_at:   datetime = Field(default_factory=_now)
    updated_at:   datetime = Field(default_factory=_now)


class Dispute(BaseModel):
    """A contributor's dispute over a contribution record (credit/attribution/quality)."""
    id:            str = Field(default_factory=_uid)
    contribution_record_id: str
    venture_unit_id: str
    raised_by:     str
    reason:        str
    requested_resolution: str = ""
    status:        DisputeStatus = DisputeStatus.OPEN
    resolution:    str = ""
    resolved_by:   Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class WeeklyReport(BaseModel):
    """Factual, non-promissory venture report. Drafted by the Report agent;
    publishing externally requires an explicit human approval."""
    id:            str = Field(default_factory=_uid)
    venture_unit_id: str
    period:        str = "weekly"
    content:       dict[str, Any] = Field(default_factory=dict)
    disclaimer:    str = ""
    published:     bool = False
    approved_by:   Optional[str] = None
    created_at:    datetime = Field(default_factory=_now)
    updated_at:    datetime = Field(default_factory=_now)


class VoundryAuditEvent(BaseModel):
    id:            str = Field(default_factory=_uid)
    actor_id:      str
    actor_type:    str            # human | ai | system
    action:        str
    resource_type: str
    resource_id:   str
    detail:        str = ""
    metadata:      dict[str, Any] = Field(default_factory=dict)
    created_at:    datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Judgment labor — humans as the credited governance organ of a venture
# ---------------------------------------------------------------------------


class JudgmentType(str, Enum):
    """The classes of human judgment the governance model requires."""
    GEL_APPROVAL      = "gel_approval"        # approve/deny a GEL-gated action
    QUALITY_REVIEW    = "quality_review"      # verdict on a submitted deliverable
    KILL_CONTINUE     = "kill_continue"       # venture kill-criteria verdict
    ESCALATION_REVIEW = "escalation_review"   # dispute/escalation ruling
    RELEASE_SIGNOFF   = "release_signoff"     # milestone/graduation gate


class JudgmentTaskStatus(str, Enum):
    OPEN      = "open"
    CLAIMED   = "claimed"
    DECIDED   = "decided"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class JudgmentVerdict(str, Enum):
    APPROVE  = "approve"
    DENY     = "deny"
    KILL     = "kill"
    CONTINUE = "continue"


class VestingStatus(str, Enum):
    """Judgment credits vest 25% on decision, 75% after the accountability window."""
    PARTIAL  = "partial"    # 25% vested, 75% pending the window
    VESTED   = "vested"     # judgment aged well — fully vested
    REVERSED = "reversed"   # judgment reversed in-window — unvested cancelled + slash


VALID_JUDGMENT_TASK_TRANSITIONS: dict[JudgmentTaskStatus, frozenset[JudgmentTaskStatus]] = {
    JudgmentTaskStatus.OPEN:      frozenset({JudgmentTaskStatus.CLAIMED, JudgmentTaskStatus.ESCALATED, JudgmentTaskStatus.CANCELLED}),
    JudgmentTaskStatus.CLAIMED:   frozenset({JudgmentTaskStatus.OPEN, JudgmentTaskStatus.DECIDED, JudgmentTaskStatus.ESCALATED, JudgmentTaskStatus.CANCELLED}),
    JudgmentTaskStatus.ESCALATED: frozenset({JudgmentTaskStatus.DECIDED, JudgmentTaskStatus.CANCELLED}),
    JudgmentTaskStatus.DECIDED:   frozenset(),
    JudgmentTaskStatus.CANCELLED: frozenset(),
}

VALID_VESTING_TRANSITIONS: dict[VestingStatus, frozenset[VestingStatus]] = {
    VestingStatus.PARTIAL:  frozenset({VestingStatus.VESTED, VestingStatus.REVERSED}),
    VestingStatus.VESTED:   frozenset(),
    VestingStatus.REVERSED: frozenset(),
}


def validate_judgment_task_transition(current: JudgmentTaskStatus, target: JudgmentTaskStatus) -> None:
    _validate("judgment_task", VALID_JUDGMENT_TASK_TRANSITIONS, current, target)


def validate_vesting_transition(current: VestingStatus, target: VestingStatus) -> None:
    _validate("judgment_vesting", VALID_VESTING_TRANSITIONS, current, target)


class JudgmentTask(BaseModel):
    """
    A system-spawned request for human judgment on a gated event.

    Never hand-authored: the service spawns one whenever governance requires a
    human call (GEL gate, human review, kill review, dispute escalation,
    graduation). Contributor judgments are ADVISORY-INTO-GEL — consensus here
    never satisfies the GEL gate itself; the operator remains the terminus.
    """
    id:              str = Field(default_factory=_uid)
    judgment_type:   JudgmentType
    subject_type:    str                       # candidate | submission | contribution | venture | dispute
    subject_id:      str
    venture_unit_id: Optional[str] = None
    candidate_id:    Optional[str] = None
    gel_task_id:     Optional[str] = None      # linked GEL approval task (advisory target)
    gel_contract_id: Optional[str] = None
    stake_multiplier: float = 1.0
    required_judgments: int = 1                # 2 = two-key rule
    min_tier:        ContributorTier = ContributorTier.VENTURE_LEAD
    status:          JudgmentTaskStatus = JudgmentTaskStatus.OPEN
    active_claims:   list[dict[str, Any]] = Field(default_factory=list)   # {judge_id, claimed_at, deadline}
    consensus_verdict: Optional[JudgmentVerdict] = None
    escalation_reason: str = ""
    context:         dict[str, Any] = Field(default_factory=dict)         # COI facts captured at spawn
    decided_at:      Optional[datetime] = None
    created_at:      datetime = Field(default_factory=_now)
    updated_at:      datetime = Field(default_factory=_now)


class JudgmentRecord(BaseModel):
    """
    Transparent record of one human judgment and its earned credits.

    Judgment credits are earned on outcome, not on click: 25% vests on
    decision, 75% after the accountability window if the judgment aged well.
    A reversal in-window cancels the unvested portion AND slashes the vested
    portion. Exposes every component (no invisible scoring). Has NO transfer
    field or method: credits are non-transferable recognition units.
    """
    id:              str = Field(default_factory=_uid)
    judgment_task_id: str
    judgment_type:   JudgmentType
    judge_id:        str
    venture_unit_id: Optional[str] = None
    verdict:         JudgmentVerdict
    rationale:       str = Field(..., min_length=140)
    j_base:          float
    stake_multiplier: float
    timeliness_multiplier: float
    track_record_multiplier: float
    total_credits:   int
    vested_credits:  int
    unvested_credits: int
    slash_credits:   int = 0
    vesting_status:  VestingStatus = VestingStatus.PARTIAL
    window_ends_at:  datetime
    outcome:         str = "pending"           # pending | aged_well | reversed
    outcome_detail:  str = ""
    settled_at:      Optional[datetime] = None
    created_at:      datetime = Field(default_factory=_now)
    updated_at:      datetime = Field(default_factory=_now)


# ---------------------------------------------------------------------------
# Legal & consent — versioned documents + click-wrap signature receipts
# ---------------------------------------------------------------------------


class LegalDocumentKind(str, Enum):
    TERMS_OF_PARTICIPATION         = "terms_of_participation"
    CONTRIBUTION_CREDITS_AGREEMENT = "contribution_credits_agreement"
    IP_ASSIGNMENT                  = "ip_assignment"
    PLATFORM_NDA                   = "platform_nda"
    VENTURE_NDA                    = "venture_nda"


class LegalScope(str, Enum):
    PLATFORM = "platform"
    VENTURE  = "venture"


class LegalDocument(BaseModel):
    """A versioned legal document; the body is content-hashed so every
    signature can be verified against exactly what was shown."""
    id:             str = Field(default_factory=_uid)
    kind:           LegalDocumentKind
    scope:          LegalScope = LegalScope.PLATFORM
    version:        str = "1.0"
    title:          str
    body:           str
    content_sha256: str
    candidate_id:   Optional[str] = None       # set for venture-scoped NDAs
    active:         bool = True
    created_at:     datetime = Field(default_factory=_now)


class SignatureRecord(BaseModel):
    """
    A click-wrap electronic signature receipt. Insert-only (WORM): a signature
    is never updated or deleted. The document hash binds the signature to the
    exact text signed; ip/user_agent live here only (never in audit metadata).
    """
    id:              str = Field(default_factory=_uid)
    account_id:      str
    document_id:     str
    document_kind:   LegalDocumentKind
    document_version: str
    document_sha256: str
    typed_name:      str
    ip_address:      str = ""
    user_agent:      str = ""
    signed_at:       datetime = Field(default_factory=_now)
