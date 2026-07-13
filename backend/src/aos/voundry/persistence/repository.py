"""
Voundry persistence repository — write-through, DB is the source of truth.

Unlike the mission pipeline (which keeps in-memory state and persists
asynchronously), Voundry entities are authoritative in the database: the service
reads and writes them directly. Mutable entities (status transitions) are
UPSERTed via session.merge; the audit trail is insert-only.

Sessions are opened and closed per operation (no long-lived session state),
matching src/aos/missions/persistence/repository.py.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from src.core.registry.database import get_session
from src.aos.voundry.persistence import models as m


class VoundryRepository:
    """Write-through repository for all Voundry entities."""

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge(record) -> None:
        session = get_session()
        try:
            session.merge(record)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _get(model_cls, pk: str) -> Optional[dict]:
        session = get_session()
        try:
            row = session.get(model_cls, pk)
            return dict(row.payload) if row is not None else None
        finally:
            session.close()

    @staticmethod
    def _list(model_cls, *, where: Optional[dict] = None) -> list[dict]:
        session = get_session()
        try:
            q = session.query(model_cls)
            if where:
                q = q.filter_by(**where)
            return [dict(r.payload) for r in q.all()]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Ideas
    # ------------------------------------------------------------------

    def save_idea(self, idea) -> None:
        self._merge(m.VoundryIdeaRecord(
            id=idea.id, submitted_by=idea.submitted_by,
            status=idea.status.value, created_at=idea.created_at,
            payload=idea.model_dump(mode="json"),
        ))

    def get_idea(self, idea_id: str) -> Optional[dict]:
        return self._get(m.VoundryIdeaRecord, idea_id)

    def list_ideas(self) -> list[dict]:
        return self._list(m.VoundryIdeaRecord)

    # ------------------------------------------------------------------
    # Screening reports
    # ------------------------------------------------------------------

    def save_screening(self, report) -> None:
        self._merge(m.VoundryScreeningRecord(
            id=report.id, idea_id=report.idea_id, verdict=report.verdict,
            created_at=report.created_at, payload=report.model_dump(mode="json"),
        ))

    def list_screening_for_idea(self, idea_id: str) -> list[dict]:
        return self._list(m.VoundryScreeningRecord, where={"idea_id": idea_id})

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------

    def save_candidate(self, candidate) -> None:
        self._merge(m.VoundryCandidateRecord(
            id=candidate.id, idea_id=candidate.idea_id,
            status=candidate.status.value, created_at=candidate.created_at,
            payload=candidate.model_dump(mode="json"),
        ))

    def get_candidate(self, candidate_id: str) -> Optional[dict]:
        return self._get(m.VoundryCandidateRecord, candidate_id)

    def list_candidates(self) -> list[dict]:
        return self._list(m.VoundryCandidateRecord)

    # ------------------------------------------------------------------
    # Venture units
    # ------------------------------------------------------------------

    def save_venture(self, venture) -> None:
        self._merge(m.VoundryVentureRecord(
            id=venture.id, candidate_id=venture.candidate_id,
            status=venture.status.value, created_at=venture.created_at,
            payload=venture.model_dump(mode="json"),
        ))

    def get_venture(self, venture_id: str) -> Optional[dict]:
        return self._get(m.VoundryVentureRecord, venture_id)

    def list_ventures(self) -> list[dict]:
        return self._list(m.VoundryVentureRecord)

    # ------------------------------------------------------------------
    # Milestones
    # ------------------------------------------------------------------

    def save_milestone(self, milestone) -> None:
        self._merge(m.VoundryMilestoneRecord(
            id=milestone.id, venture_unit_id=milestone.venture_unit_id,
            status=milestone.status.value, created_at=milestone.created_at,
            payload=milestone.model_dump(mode="json"),
        ))

    def get_milestone(self, milestone_id: str) -> Optional[dict]:
        return self._get(m.VoundryMilestoneRecord, milestone_id)

    def list_milestones_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryMilestoneRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # Work units
    # ------------------------------------------------------------------

    def save_work_unit(self, work_unit) -> None:
        self._merge(m.VoundryWorkUnitRecord(
            id=work_unit.id, venture_unit_id=work_unit.venture_unit_id,
            milestone_id=work_unit.milestone_id, status=work_unit.status.value,
            created_at=work_unit.created_at, payload=work_unit.model_dump(mode="json"),
        ))

    def get_work_unit(self, work_unit_id: str) -> Optional[dict]:
        return self._get(m.VoundryWorkUnitRecord, work_unit_id)

    def list_work_units_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryWorkUnitRecord, where={"venture_unit_id": venture_id})

    def list_work_units(self) -> list[dict]:
        return self._list(m.VoundryWorkUnitRecord)

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------

    def save_application(self, application) -> None:
        self._merge(m.VoundryApplicationRecord(
            id=application.id, work_unit_id=application.work_unit_id,
            contributor_id=application.contributor_id, status=application.status.value,
            created_at=application.created_at, payload=application.model_dump(mode="json"),
        ))

    def get_application(self, application_id: str) -> Optional[dict]:
        return self._get(m.VoundryApplicationRecord, application_id)

    def list_applications_for_work_unit(self, work_unit_id: str) -> list[dict]:
        return self._list(m.VoundryApplicationRecord, where={"work_unit_id": work_unit_id})

    # ------------------------------------------------------------------
    # Submissions
    # ------------------------------------------------------------------

    def save_submission(self, submission) -> None:
        self._merge(m.VoundrySubmissionRecord(
            id=submission.id, work_unit_id=submission.work_unit_id,
            contributor_id=submission.contributor_id, status=submission.status.value,
            created_at=submission.created_at, payload=submission.model_dump(mode="json"),
        ))

    def get_submission(self, submission_id: str) -> Optional[dict]:
        return self._get(m.VoundrySubmissionRecord, submission_id)

    def list_submissions_for_work_unit(self, work_unit_id: str) -> list[dict]:
        return self._list(m.VoundrySubmissionRecord, where={"work_unit_id": work_unit_id})

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def save_review(self, review) -> None:
        self._merge(m.VoundryReviewRecord(
            id=review.id, submission_id=review.submission_id,
            reviewer_type=review.reviewer_type.value, created_at=review.created_at,
            payload=review.model_dump(mode="json"),
        ))

    def list_reviews_for_submission(self, submission_id: str) -> list[dict]:
        return self._list(m.VoundryReviewRecord, where={"submission_id": submission_id})

    # ------------------------------------------------------------------
    # Contribution records (ledger)
    # ------------------------------------------------------------------

    def save_contribution(self, record) -> None:
        self._merge(m.VoundryContributionRecord(
            id=record.id, venture_unit_id=record.venture_unit_id,
            work_unit_id=record.work_unit_id, contributor_id=record.contributor_id,
            approval_status=record.approval_status.value, created_at=record.created_at,
            payload=record.model_dump(mode="json"),
        ))

    def get_contribution(self, record_id: str) -> Optional[dict]:
        return self._get(m.VoundryContributionRecord, record_id)

    def list_contributions_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryContributionRecord, where={"venture_unit_id": venture_id})

    def list_contributions_for_contributor(self, contributor_id: str) -> list[dict]:
        return self._list(m.VoundryContributionRecord, where={"contributor_id": contributor_id})

    # ------------------------------------------------------------------
    # Decision log
    # ------------------------------------------------------------------

    def save_decision_log(self, entry) -> None:
        self._merge(m.VoundryDecisionLogRecord(
            id=entry.id, venture_unit_id=entry.venture_unit_id,
            decision_type=entry.decision_type, created_at=entry.created_at,
            payload=entry.model_dump(mode="json"),
        ))

    def list_decision_log_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryDecisionLogRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # Risk register
    # ------------------------------------------------------------------

    def save_risk(self, risk) -> None:
        self._merge(m.VoundryRiskRecord(
            id=risk.id, venture_unit_id=risk.venture_unit_id,
            severity=risk.severity.value, created_at=risk.created_at,
            payload=risk.model_dump(mode="json"),
        ))

    def get_risk(self, risk_id: str) -> Optional[dict]:
        return self._get(m.VoundryRiskRecord, risk_id)

    def list_risks_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryRiskRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # App accounts (auth)
    # ------------------------------------------------------------------

    def save_voundry_account(self, account: dict) -> None:
        session = get_session()
        try:
            rec = m.VoundryAccountRecord(
                account_id=account["account_id"], email=account["email"],
                role=account["role"], payload=account,
            )
            session.merge(rec)
            session.commit()
        finally:
            session.close()

    def get_voundry_account(self, account_id: str) -> Optional[dict]:
        session = get_session()
        try:
            row = session.get(m.VoundryAccountRecord, account_id)
            return dict(row.payload) if row else None
        finally:
            session.close()

    def get_voundry_account_by_email(self, email: str) -> Optional[dict]:
        session = get_session()
        try:
            row = (
                session.query(m.VoundryAccountRecord)
                .filter_by(email=email.strip().lower())
                .first()
            )
            return dict(row.payload) if row else None
        finally:
            session.close()

    def list_voundry_accounts(self) -> list[dict]:
        session = get_session()
        try:
            return [dict(r.payload) for r in session.query(m.VoundryAccountRecord).all()]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Verification requests
    # ------------------------------------------------------------------

    def save_verification(self, req) -> None:
        self._merge(m.VoundryVerificationRecord(
            id=req.id, contributor_id=req.contributor_id, status=req.status.value,
            created_at=req.created_at, payload=req.model_dump(mode="json"),
        ))

    def get_verification(self, req_id: str) -> Optional[dict]:
        return self._get(m.VoundryVerificationRecord, req_id)

    def list_verifications(self) -> list[dict]:
        return self._list(m.VoundryVerificationRecord)

    # ------------------------------------------------------------------
    # Contributor profiles
    # ------------------------------------------------------------------

    def save_contributor(self, profile) -> None:
        self._merge(m.VoundryContributorRecord(
            contributor_id=profile.contributor_id, tier=profile.tier.value,
            created_at=profile.created_at, payload=profile.model_dump(mode="json"),
        ))

    def get_contributor(self, contributor_id: str) -> Optional[dict]:
        return self._get(m.VoundryContributorRecord, contributor_id)

    def list_contributors(self) -> list[dict]:
        return self._list(m.VoundryContributorRecord)

    # ------------------------------------------------------------------
    # Trust Center page overrides
    # ------------------------------------------------------------------

    def save_trust_page(self, slug: str, *, title: str, body: str) -> None:
        self._merge(m.VoundryTrustPageRecord(slug=slug, title=title, body=body))

    def get_trust_page(self, slug: str) -> Optional[dict]:
        session = get_session()
        try:
            row = session.get(m.VoundryTrustPageRecord, slug)
            return {"slug": row.slug, "title": row.title, "body": row.body} if row else None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Weekly reports
    # ------------------------------------------------------------------

    def save_report(self, report) -> None:
        self._merge(m.VoundryReportRecord(
            id=report.id, venture_unit_id=report.venture_unit_id,
            published=str(report.published).lower(), created_at=report.created_at,
            payload=report.model_dump(mode="json"),
        ))

    def get_report(self, report_id: str) -> Optional[dict]:
        return self._get(m.VoundryReportRecord, report_id)

    def list_reports_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryReportRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # IP registry
    # ------------------------------------------------------------------

    def save_ip(self, item) -> None:
        self._merge(m.VoundryIPRecord(
            id=item.id, venture_unit_id=item.venture_unit_id, ip_mode=item.ip_mode.value,
            status=item.status, created_at=item.created_at, payload=item.model_dump(mode="json"),
        ))

    def get_ip(self, item_id: str) -> Optional[dict]:
        return self._get(m.VoundryIPRecord, item_id)

    def list_ip_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryIPRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # Workspace messages
    # ------------------------------------------------------------------

    def save_message(self, msg) -> None:
        self._merge(m.VoundryWorkspaceMessageRecord(
            id=msg.id, work_unit_id=msg.work_unit_id, venture_unit_id=msg.venture_unit_id,
            created_at=msg.created_at, payload=msg.model_dump(mode="json"),
        ))

    def list_messages_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundryWorkspaceMessageRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""))

    # ------------------------------------------------------------------
    # Votes (one per candidate+voter)
    # ------------------------------------------------------------------

    def save_vote(self, vote) -> None:
        self._merge(m.VoundryVoteRecord(
            id=vote.id, candidate_id=vote.candidate_id, voter_id=vote.voter_id,
            audience=vote.audience.value, created_at=vote.created_at,
            payload=vote.model_dump(mode="json"),
        ))

    def list_votes_for_candidate(self, candidate_id: str) -> list[dict]:
        return self._list(m.VoundryVoteRecord, where={"candidate_id": candidate_id})

    def get_vote(self, candidate_id: str, voter_id: str) -> Optional[dict]:
        session = get_session()
        try:
            row = (
                session.query(m.VoundryVoteRecord)
                .filter_by(candidate_id=candidate_id, voter_id=voter_id)
                .first()
            )
            return dict(row.payload) if row else None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Disputes
    # ------------------------------------------------------------------

    def save_dispute(self, dispute) -> None:
        self._merge(m.VoundryDisputeRecord(
            id=dispute.id, contribution_record_id=dispute.contribution_record_id,
            venture_unit_id=dispute.venture_unit_id, status=dispute.status.value,
            created_at=dispute.created_at, payload=dispute.model_dump(mode="json"),
        ))

    def get_dispute(self, dispute_id: str) -> Optional[dict]:
        return self._get(m.VoundryDisputeRecord, dispute_id)

    def list_disputes(self) -> list[dict]:
        return self._list(m.VoundryDisputeRecord)

    def list_disputes_for_record(self, record_id: str) -> list[dict]:
        return self._list(m.VoundryDisputeRecord, where={"contribution_record_id": record_id})

    # ------------------------------------------------------------------
    # Investor pledges
    # ------------------------------------------------------------------

    def save_pledge(self, pledge) -> None:
        self._merge(m.VoundryInvestorPledgeRecord(
            id=pledge.id, investor_id=pledge.investor_id,
            venture_unit_id=pledge.venture_unit_id, pledge_type=pledge.pledge_type.value,
            status=pledge.status.value, created_at=pledge.created_at,
            payload=pledge.model_dump(mode="json"),
        ))

    def get_pledge(self, pledge_id: str) -> Optional[dict]:
        return self._get(m.VoundryInvestorPledgeRecord, pledge_id)

    def list_pledges(self) -> list[dict]:
        return self._list(m.VoundryInvestorPledgeRecord)

    def list_pledges_for_venture(self, venture_id: str) -> list[dict]:
        return self._list(m.VoundryInvestorPledgeRecord, where={"venture_unit_id": venture_id})

    # ------------------------------------------------------------------
    # Audit (append-only)
    # ------------------------------------------------------------------

    def append_audit(self, event) -> None:
        """Insert-only. The audit trail is WORM — never merged or updated."""
        session = get_session()
        try:
            rec = m.VoundryAuditRecord(
                id=event.id or str(uuid.uuid4()),
                actor_id=event.actor_id, action=event.action,
                resource_type=event.resource_type, resource_id=event.resource_id,
                created_at=event.created_at, payload=event.model_dump(mode="json"),
            )
            session.add(rec)
            session.commit()
        finally:
            session.close()

    def list_audit(self, *, limit: int = 500) -> list[dict]:
        session = get_session()
        try:
            rows = (
                session.query(m.VoundryAuditRecord)
                .order_by(m.VoundryAuditRecord.created_at.asc())
                .limit(limit)
                .all()
            )
            return [dict(r.payload) for r in rows]
        finally:
            session.close()

    def list_audit_recent(self, *, limit: int = 200) -> list[dict]:
        """Most-recent-first audit slice (feed projections)."""
        session = get_session()
        try:
            rows = (
                session.query(m.VoundryAuditRecord)
                .order_by(m.VoundryAuditRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [dict(r.payload) for r in rows]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Judgment tasks
    # ------------------------------------------------------------------

    def save_judgment_task(self, task) -> None:
        self._merge(m.VoundryJudgmentTaskRecord(
            id=task.id, judgment_type=task.judgment_type.value,
            subject_id=task.subject_id, venture_unit_id=task.venture_unit_id,
            status=task.status.value, created_at=task.created_at,
            payload=task.model_dump(mode="json"),
        ))

    def get_judgment_task(self, task_id: str) -> Optional[dict]:
        return self._get(m.VoundryJudgmentTaskRecord, task_id)

    def list_judgment_tasks(self, *, status: Optional[str] = None) -> list[dict]:
        where = {"status": status} if status else None
        return self._list(m.VoundryJudgmentTaskRecord, where=where)

    def list_judgment_tasks_for_subject(self, subject_id: str) -> list[dict]:
        return self._list(m.VoundryJudgmentTaskRecord, where={"subject_id": subject_id})

    # ------------------------------------------------------------------
    # Judgment credit records (ledger)
    # ------------------------------------------------------------------

    def save_judgment_record(self, record) -> None:
        self._merge(m.VoundryJudgmentCreditRecord(
            id=record.id, judgment_task_id=record.judgment_task_id,
            judge_id=record.judge_id, vesting_status=record.vesting_status.value,
            created_at=record.created_at, payload=record.model_dump(mode="json"),
        ))

    def get_judgment_record(self, record_id: str) -> Optional[dict]:
        return self._get(m.VoundryJudgmentCreditRecord, record_id)

    def list_judgment_records_for_judge(self, judge_id: str) -> list[dict]:
        return self._list(m.VoundryJudgmentCreditRecord, where={"judge_id": judge_id})

    def list_judgment_records_for_task(self, task_id: str) -> list[dict]:
        return self._list(m.VoundryJudgmentCreditRecord, where={"judgment_task_id": task_id})

    def list_judgment_records(self, *, vesting_status: Optional[str] = None) -> list[dict]:
        where = {"vesting_status": vesting_status} if vesting_status else None
        return self._list(m.VoundryJudgmentCreditRecord, where=where)

    # ------------------------------------------------------------------
    # Legal documents
    # ------------------------------------------------------------------

    def save_legal_document(self, doc) -> None:
        self._merge(m.VoundryLegalDocumentRecord(
            id=doc.id, kind=doc.kind.value, scope=doc.scope.value,
            candidate_id=doc.candidate_id, active=str(doc.active).lower(),
            version=doc.version, created_at=doc.created_at,
            payload=doc.model_dump(mode="json"),
        ))

    def get_legal_document(self, document_id: str) -> Optional[dict]:
        return self._get(m.VoundryLegalDocumentRecord, document_id)

    def list_legal_documents(
        self,
        *,
        kind: Optional[str] = None,
        scope: Optional[str] = None,
        candidate_id: Optional[str] = None,
        active_only: bool = True,
    ) -> list[dict]:
        where: dict = {}
        if kind:
            where["kind"] = kind
        if scope:
            where["scope"] = scope
        if candidate_id:
            where["candidate_id"] = candidate_id
        if active_only:
            where["active"] = "true"
        return self._list(m.VoundryLegalDocumentRecord, where=where or None)

    # ------------------------------------------------------------------
    # Signature records (insert-only)
    # ------------------------------------------------------------------

    def append_signature(self, sig) -> None:
        """Insert-only. Signatures are WORM receipts — never merged or updated."""
        session = get_session()
        try:
            rec = m.VoundrySignatureRecord(
                id=sig.id, account_id=sig.account_id, document_id=sig.document_id,
                created_at=sig.signed_at, payload=sig.model_dump(mode="json"),
            )
            session.add(rec)
            session.commit()
        finally:
            session.close()

    def list_signatures_for_account(self, account_id: str) -> list[dict]:
        return self._list(m.VoundrySignatureRecord, where={"account_id": account_id})

    def get_signature_for_document(self, account_id: str, document_id: str) -> Optional[dict]:
        session = get_session()
        try:
            row = (
                session.query(m.VoundrySignatureRecord)
                .filter_by(account_id=account_id, document_id=document_id)
                .first()
            )
            return dict(row.payload) if row else None
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Agent runs (insert-only log)
    # ------------------------------------------------------------------

    def save_agent_run(self, run) -> None:
        self._merge(m.VoundryAgentRunRecord(
            id=run.id, contributor_id=run.contributor_id, work_unit_id=run.work_unit_id,
            agent_key=run.agent_key, created_at=run.created_at,
            payload=run.model_dump(mode="json"),
        ))

    def list_agent_runs_for_work_unit(self, work_unit_id: str) -> list[dict]:
        return self._list(m.VoundryAgentRunRecord, where={"work_unit_id": work_unit_id})

    # ------------------------------------------------------------------
    # Workspace files (editable, deletable)
    # ------------------------------------------------------------------

    def save_workspace_file(self, f) -> None:
        self._merge(m.VoundryWorkspaceFileRecord(
            id=f.id, work_unit_id=f.work_unit_id, contributor_id=f.contributor_id,
            created_at=f.created_at, payload=f.model_dump(mode="json"),
        ))

    def get_workspace_file(self, file_id: str) -> Optional[dict]:
        return self._get(m.VoundryWorkspaceFileRecord, file_id)

    def list_workspace_files_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundryWorkspaceFileRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)

    def delete_workspace_file(self, file_id: str) -> None:
        session = get_session()
        try:
            row = session.get(m.VoundryWorkspaceFileRecord, file_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Intake interviews
    # ------------------------------------------------------------------

    def save_interview(self, session) -> None:
        self._merge(m.VoundryInterviewRecord(
            id=session.id, contributor_id=session.contributor_id,
            status=session.status.value if hasattr(session.status, "value") else session.status,
            created_at=session.created_at, payload=session.model_dump(mode="json"),
        ))

    def get_interview(self, session_id: str) -> Optional[dict]:
        return self._get(m.VoundryInterviewRecord, session_id)

    # ------------------------------------------------------------------
    # Connected tools (governed external connectors)
    # ------------------------------------------------------------------

    def save_connected_tool(self, tool) -> None:
        self._merge(m.VoundryConnectedToolRecord(
            id=tool.id, work_unit_id=tool.work_unit_id, contributor_id=tool.contributor_id,
            connector_key=tool.connector_key, created_at=tool.created_at,
            payload=tool.model_dump(mode="json"),
        ))

    def get_connected_tool(self, tool_id: str) -> Optional[dict]:
        return self._get(m.VoundryConnectedToolRecord, tool_id)

    def list_connected_tools_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundryConnectedToolRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""))

    def delete_connected_tool(self, tool_id: str) -> None:
        session = get_session()
        try:
            row = session.get(m.VoundryConnectedToolRecord, tool_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Connector write requests (governed, human-approved write-back)
    # ------------------------------------------------------------------

    def save_write_request(self, req) -> None:
        self._merge(m.VoundryWriteRequestRecord(
            id=req.id, work_unit_id=req.work_unit_id, contributor_id=req.contributor_id,
            status=req.status.value if hasattr(req.status, "value") else req.status,
            created_at=req.requested_at, payload=req.model_dump(mode="json"),
        ))

    def get_write_request(self, request_id: str) -> Optional[dict]:
        return self._get(m.VoundryWriteRequestRecord, request_id)

    def list_write_requests_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundryWriteRequestRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("requested_at", ""), reverse=True)

    def list_pending_write_requests(self) -> list[dict]:
        rows = self._list(m.VoundryWriteRequestRecord, where={"status": "pending"})
        return sorted(rows, key=lambda x: x.get("requested_at", ""), reverse=True)

    # ------------------------------------------------------------------
    # Connector bridges + jobs (on-prem plug-n-play connectivity)
    # ------------------------------------------------------------------

    def save_bridge(self, bridge) -> None:
        self._merge(m.VoundryBridgeRecord(
            id=bridge.id, work_unit_id=bridge.work_unit_id, contributor_id=bridge.contributor_id,
            created_at=bridge.created_at, payload=bridge.model_dump(mode="json")))

    def get_bridge(self, bridge_id: str) -> Optional[dict]:
        return self._get(m.VoundryBridgeRecord, bridge_id)

    def delete_bridge(self, bridge_id: str) -> None:
        session = get_session()
        try:
            row = session.get(m.VoundryBridgeRecord, bridge_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    def list_bridges_for_work_unit(self, work_unit_id: str) -> list[dict]:
        return self._list(m.VoundryBridgeRecord, where={"work_unit_id": work_unit_id})

    def list_all_bridges(self) -> list[dict]:
        return self._list(m.VoundryBridgeRecord, where={})

    # ------------------------------------------------------------------
    # Saved SQL queries
    # ------------------------------------------------------------------

    def save_query(self, q) -> None:
        self._merge(m.VoundrySavedQueryRecord(
            id=q.id, work_unit_id=q.work_unit_id, contributor_id=q.contributor_id,
            created_at=q.created_at, payload=q.model_dump(mode="json")))

    def get_query(self, query_id: str) -> Optional[dict]:
        return self._get(m.VoundrySavedQueryRecord, query_id)

    def get_org_policy(self) -> Optional[dict]:
        return self._get(m.VoundryOrgPolicyRecord, "org")

    def save_org_policy(self, payload: dict) -> None:
        self._merge(m.VoundryOrgPolicyRecord(id="org", payload=payload))

    # Small KV (reuses the policy table) — e.g. the WACE audit signing key.
    def get_kv(self, key: str) -> Optional[dict]:
        return self._get(m.VoundryOrgPolicyRecord, key)

    def save_kv(self, key: str, payload: dict) -> None:
        self._merge(m.VoundryOrgPolicyRecord(id=key, payload=payload))

    def claim_saml_assertion(self, assertion_id: str, expiry_ts: float) -> bool:
        """Atomically record a SAML assertion id as consumed (cross-worker replay
        guard). Returns True the first time (claim succeeded), False if it was
        already seen. Relies on the KV table's primary-key uniqueness, so the
        check-and-set is atomic even across uvicorn workers."""
        from sqlalchemy.exc import IntegrityError
        session = get_session()
        try:
            session.add(m.VoundryOrgPolicyRecord(id=f"saml_seen:{assertion_id}",
                                                 payload={"exp": float(expiry_ts)}))
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False
        finally:
            session.close()

    def purge_expired_saml_assertions(self, now_ts: float) -> None:
        session = get_session()
        try:
            rows = (session.query(m.VoundryOrgPolicyRecord)
                    .filter(m.VoundryOrgPolicyRecord.id.like("saml_seen:%")).all())
            for r in rows:
                if float((r.payload or {}).get("exp", 0)) <= now_ts:
                    session.delete(r)
            session.commit()
        finally:
            session.close()

    def list_queries_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundrySavedQueryRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""))

    def delete_query(self, query_id: str) -> None:
        session = get_session()
        try:
            row = session.get(m.VoundrySavedQueryRecord, query_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Terminal runbooks (saved diagnostic command sets)
    # ------------------------------------------------------------------

    def save_runbook(self, rb) -> None:
        self._merge(m.VoundryTerminalRunbookRecord(
            id=rb.id, work_unit_id=rb.work_unit_id, contributor_id=rb.contributor_id,
            created_at=rb.created_at, payload=rb.model_dump(mode="json")))

    def get_runbook(self, runbook_id: str) -> Optional[dict]:
        return self._get(m.VoundryTerminalRunbookRecord, runbook_id)

    def list_runbooks_for_work_unit(self, work_unit_id: str) -> list[dict]:
        rows = self._list(m.VoundryTerminalRunbookRecord, where={"work_unit_id": work_unit_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""))

    def delete_runbook(self, runbook_id: str) -> None:
        session = get_session()
        try:
            row = session.get(m.VoundryTerminalRunbookRecord, runbook_id)
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    def save_bridge_job(self, job) -> None:
        self._merge(m.VoundryBridgeJobRecord(
            id=job.id, bridge_id=job.bridge_id,
            status=job.status.value if hasattr(job.status, "value") else job.status,
            created_at=job.created_at, payload=job.model_dump(mode="json")))

    def get_bridge_job(self, job_id: str) -> Optional[dict]:
        return self._get(m.VoundryBridgeJobRecord, job_id)

    def list_pending_jobs_for_bridge(self, bridge_id: str) -> list[dict]:
        rows = self._list(m.VoundryBridgeJobRecord, where={"bridge_id": bridge_id, "status": "pending"})
        return sorted(rows, key=lambda x: x.get("created_at", ""))

    def list_recent_jobs_for_bridge(self, bridge_id: str, limit: int = 20) -> list[dict]:
        rows = self._list(m.VoundryBridgeJobRecord, where={"bridge_id": bridge_id})
        return sorted(rows, key=lambda x: x.get("created_at", ""), reverse=True)[:limit]


# Module-level singleton
voundry_repo = VoundryRepository()
