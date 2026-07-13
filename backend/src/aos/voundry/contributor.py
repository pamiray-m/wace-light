"""
Voundry contributor profiles + 6-tier model (blueprint §5.2).

Tiers (ascending): Observer → Applicant → Verified → Senior → Venture Lead →
Certified AOS Operator. Tiers are domain records, not auth principals: who *acts*
is the authenticated operator; the tier governs *eligibility* (Observers cannot
take work; only Verified+ may be assigned). Promotion is a human-approved action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.aos.voundry.contracts import (
    ContributorProfile,
    ContributorTier,
    VerificationRequest,
    VerificationStatus,
)
from src.aos.voundry.governance import voundry_audit
from src.aos.voundry.persistence.repository import voundry_repo

TIER_ORDER: list[ContributorTier] = [
    ContributorTier.OBSERVER,
    ContributorTier.APPLICANT,
    ContributorTier.VERIFIED,
    ContributorTier.SENIOR,
    ContributorTier.VENTURE_LEAD,
    ContributorTier.AOS_OPERATOR,
]


def tier_rank(tier: ContributorTier) -> int:
    return TIER_ORDER.index(tier)


def can_apply(tier: ContributorTier) -> bool:
    """Applicant and above may apply to work units; Observers may not."""
    return tier_rank(tier) >= tier_rank(ContributorTier.APPLICANT)


def can_be_assigned(tier: ContributorTier) -> bool:
    """Verified and above may be assigned to work units."""
    return tier_rank(tier) >= tier_rank(ContributorTier.VERIFIED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContributorNotFound(Exception):
    pass


class ContributorService:
    def __init__(self, repo=voundry_repo, audit=voundry_audit) -> None:
        self._repo = repo
        self._audit = audit

    def register(
        self, contributor_id: str, *, display_name: str = "",
        skills: Optional[list[str]] = None, tier: ContributorTier = ContributorTier.APPLICANT,
    ) -> ContributorProfile:
        profile = ContributorProfile(
            contributor_id=contributor_id, display_name=display_name,
            skills=skills or [], tier=tier,
        )
        self._repo.save_contributor(profile)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="contributor.registered",
            resource_type="contributor", resource_id=contributor_id, detail=tier.value,
        )
        return profile

    def get(self, contributor_id: str) -> ContributorProfile:
        d = self._repo.get_contributor(contributor_id)
        if d is None:
            raise ContributorNotFound(contributor_id)
        return ContributorProfile(**d)

    def list(self) -> list[dict]:
        return self._repo.list_contributors()

    # -- Vetting: Applicant → Verified -------------------------------------

    def request_verification(
        self, contributor_id: str, *, portfolio_url: str = "", note: str = "",
        linkedin_url: str = "", credentials: Optional[list[str]] = None,
        cv_filename: str = "", cv_text: str = "",
    ) -> VerificationRequest:
        profile = self.get(contributor_id)  # must have a profile
        req = VerificationRequest(
            contributor_id=contributor_id, portfolio_url=portfolio_url, note=note,
            linkedin_url=linkedin_url, credentials=[c for c in (credentials or []) if c.strip()],
            cv_filename=cv_filename, cv_text=cv_text,
        )
        # Deterministic pre-approval assessment — the reviewer starts from
        # evidence; the applicant sees exactly how they were scored.
        from src.aos.voundry.assessment import assess_verification
        req.assessment = assess_verification(req, profile)
        self._repo.save_verification(req)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="verification.requested",
            resource_type="contributor", resource_id=contributor_id,
            detail=f"assessment={req.assessment['band']} ({req.assessment['score']})",
        )
        return req

    def latest_verification_score(self, contributor_id: str) -> Optional[float]:
        """The most recent verification assessment score for a contributor."""
        reqs = [
            VerificationRequest(**d)
            for d in self._repo.list_verifications()
            if d.get("contributor_id") == contributor_id
        ]
        if not reqs:
            return None
        latest = max(reqs, key=lambda r: r.created_at)
        return latest.assessment.get("score") if latest.assessment else None

    def list_verifications(self) -> list[dict]:
        return self._repo.list_verifications()

    def review_verification(
        self, request_id: str, *, approve: bool, reviewer_id: str,
    ) -> VerificationRequest:
        d = self._repo.get_verification(request_id)
        if d is None:
            raise ContributorNotFound(f"verification {request_id}")
        req = VerificationRequest(**d)
        if req.status != VerificationStatus.PENDING:
            raise ValueError("Verification already reviewed")
        req.status = VerificationStatus.APPROVED if approve else VerificationStatus.REJECTED
        req.reviewed_by = reviewer_id
        from datetime import datetime, timezone
        req.updated_at = datetime.now(timezone.utc)
        self._repo.save_verification(req)
        if approve:
            self.promote(req.contributor_id, new_tier=ContributorTier.VERIFIED, approved_by=reviewer_id)
        self._audit.append(
            actor_id=reviewer_id, actor_type="human", action="verification.reviewed",
            resource_type="contributor", resource_id=req.contributor_id,
            detail=f"approved={approve}",
        )
        try:
            from src.aos.voundry.notifications import voundry_notifier
            voundry_notifier.notify_verified(req.contributor_id, approve)
        except Exception:  # pragma: no cover
            pass
        return req

    def request_agent(
        self, contributor_id: str, *, discipline: str, agent_key: str,
    ) -> ContributorProfile:
        """Grant a requested (role-relevant, pre-vetted) agent to a contributor's
        workspace for a discipline. Self-serve but recorded."""
        from src.aos.voundry.workspace_blueprint import Discipline, agent_catalog_for
        try:
            disc = Discipline(discipline)
        except ValueError:
            raise ValueError(f"Unknown discipline '{discipline}'")
        valid = {a.key for a in agent_catalog_for(disc)}
        if agent_key not in valid:
            raise ValueError(f"'{agent_key}' is not a requestable agent for {discipline}")
        profile = self.get(contributor_id)
        added = dict(profile.added_agents)
        current = list(added.get(disc.value, []))
        if agent_key not in current:
            current.append(agent_key)
            added[disc.value] = current
            profile.added_agents = added
            profile.updated_at = _now()
            self._repo.save_contributor(profile)
            self._audit.append(
                actor_id=contributor_id, actor_type="human", action="workspace.agent_added",
                resource_type="contributor", resource_id=contributor_id,
                detail=f"{disc.value}:{agent_key}",
            )
        return profile

    def update_profile(
        self, contributor_id: str, *,
        display_name: Optional[str] = None, skills: Optional[list[str]] = None,
    ) -> ContributorProfile:
        """Contributor self-service: update display name and/or skills."""
        profile = self.get(contributor_id)
        if display_name is not None and display_name.strip():
            profile.display_name = display_name.strip()
        if skills is not None:
            profile.skills = [s.strip() for s in skills if s and s.strip()]
        profile.updated_at = _now()
        self._repo.save_contributor(profile)
        self._audit.append(
            actor_id=contributor_id, actor_type="human", action="contributor.profile_updated",
            resource_type="contributor", resource_id=contributor_id,
            detail=f"skills={len(profile.skills)}",
        )
        return profile

    def promote(
        self, contributor_id: str, *, new_tier: ContributorTier, approved_by: str,
    ) -> ContributorProfile:
        profile = self.get(contributor_id)
        old = profile.tier
        profile.tier = new_tier
        profile.updated_at = _now()
        self._repo.save_contributor(profile)
        self._audit.append(
            actor_id=approved_by, actor_type="human", action="contributor.promoted",
            resource_type="contributor", resource_id=contributor_id,
            detail=f"{old.value} → {new_tier.value}",
        )
        return profile


contributor_service = ContributorService()
