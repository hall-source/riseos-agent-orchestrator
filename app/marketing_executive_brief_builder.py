from __future__ import annotations

from typing import Any

from app.marketing_executive_brief_contract import (
    MarketingExecutiveBriefLinks,
    MarketingExecutiveBriefResponse,
    MarketingExecutiveReviewSection,
    MarketingExecutiveSummarySection,
    MarketingExecutiveSynthesisSection,
)
from app.marketing_summary import MarketingWorkflowSummary

BRIEF_TYPE = "weekly_marketing_executive_brief"
ANALYTICS_SNAPSHOT_TYPE = "analytics_snapshot"
APPROVED_NEXT_ACTION = "Mock workflow has been validated. No production action has been authorized."
REVIEW_NEXT_ACTION = "Hall should review the synthesis and approve or request changes."
PARTIAL_ANALYTICS_FINDING = "Analytics snapshot evidence is not available for this workflow."


def build_weekly_marketing_executive_brief(summary: MarketingWorkflowSummary) -> MarketingExecutiveBriefResponse:
    analytics = _analytics_snapshot(summary.evidence_packets)
    analytics_content = _artifact_content(analytics)
    scorecard = _scorecard(analytics_content)
    findings = _findings(analytics_content)
    approval_state = summary.human_approval.state
    human_approval_complete = summary.readiness.human_approval_complete

    return MarketingExecutiveBriefResponse(
        workflow_id=summary.workflow_id,
        business_unit=summary.business_unit,
        date_range_label=_string_or_none(analytics_content.get("date_range_label")),
        status=summary.status,
        approval_state=approval_state,
        approval_required=summary.approval_required,
        human_approval_complete=human_approval_complete,
        live_platform_access=False,
        write_access=False,
        not_for_real_marketing_decisions=True,
        executive_summary=_executive_summary(approval_state, human_approval_complete),
        scorecard=scorecard,
        channel_breakdown=_channel_breakdown(analytics_content),
        findings=findings,
        review=MarketingExecutiveReviewSection(
            ready=summary.review.ready,
            artifact_id=summary.review.artifact_id,
            risk_flags=summary.review.risk_flags,
            approval_recommendation=summary.review.approval_recommendation,
        ),
        synthesis=MarketingExecutiveSynthesisSection(
            ready=summary.synthesis.ready,
            artifact_id=summary.synthesis.artifact_id,
            summary=summary.synthesis.summary,
        ),
        recommended_next_action=_recommended_next_action(summary, approval_state),
        links=MarketingExecutiveBriefLinks(
            summary_url=f"/api/v1/marketing/workflows/{summary.workflow_id}/summary",
            audit_events_url=f"/api/v1/marketing/evidence/audit?workflow_id={summary.workflow_id}",
            approval_url=f"/api/v1/marketing/workflows/{summary.workflow_id}/approval",
        ),
    )


def _executive_summary(approval_state: str, human_approval_complete: bool) -> MarketingExecutiveSummarySection:
    if approval_state == "approved_mock_only" and human_approval_complete:
        return MarketingExecutiveSummarySection(
            headline="Weekly marketing snapshot has been approved.",
            summary="Read-only marketing evidence was collected, synthesized, and manually approved for mock workflow validation. No production action was authorized.",
        )
    if approval_state == "rejected_mock_only":
        return MarketingExecutiveSummarySection(
            headline="Weekly marketing snapshot was rejected.",
            summary="Read-only marketing evidence was collected and synthesized, but the mock workflow was rejected. No production action was authorized.",
        )
    if approval_state == "changes_requested_mock_only":
        return MarketingExecutiveSummarySection(
            headline="Weekly marketing snapshot needs changes.",
            summary="Read-only marketing evidence was collected and synthesized, but changes were requested before the workflow can be considered validated.",
        )
    return MarketingExecutiveSummarySection(
        headline="Weekly marketing snapshot is ready for review.",
        summary="Read-only marketing evidence was collected and synthesized. Human approval is still required before any production action.",
    )


def _recommended_next_action(summary: MarketingWorkflowSummary, approval_state: str) -> str:
    if approval_state == "approved_mock_only":
        return APPROVED_NEXT_ACTION
    if approval_state == "rejected_mock_only":
        return "Mock workflow was rejected. Review notes and revise the workflow before proceeding."
    if approval_state == "changes_requested_mock_only":
        return "Changes were requested. Update the synthesis or governance logic before proceeding."
    if summary.readiness.human_approval_ready:
        return REVIEW_NEXT_ACTION
    return summary.next_action


def _analytics_snapshot(evidence_packets: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [packet for packet in evidence_packets if _artifact_type(packet) == ANALYTICS_SNAPSHOT_TYPE]
    if not matches:
        return None
    read_only_matches = [packet for packet in matches if _artifact_content(packet).get("source_mode") == "google_sheets_readonly"]
    return (read_only_matches or matches)[-1]


def _scorecard(content: dict[str, Any]) -> dict[str, int | float]:
    metrics = content.get("metrics")
    if not isinstance(metrics, dict):
        return {}
    allowed = {"leads", "contacts_created", "deals_created", "sessions", "deal_created_rate_from_leads"}
    scorecard: dict[str, int | float] = {}
    for key in allowed:
        value = metrics.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            scorecard[key] = value
    return scorecard


def _channel_breakdown(content: dict[str, Any]) -> list[dict[str, Any]]:
    breakdown = content.get("source_breakdown")
    if not isinstance(breakdown, list):
        return []
    return [item for item in breakdown if isinstance(item, dict)]


def _findings(content: dict[str, Any]) -> list[str]:
    findings = content.get("findings")
    if isinstance(findings, list):
        values = [str(item) for item in findings if item]
        if values:
            return values
    return [PARTIAL_ANALYTICS_FINDING]


def _artifact_content(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {}
    test_results = packet.get("test_results")
    return test_results if isinstance(test_results, dict) else {}


def _artifact_type(packet: dict[str, Any]) -> str | None:
    content = _artifact_content(packet)
    value = content.get("artifact_type") or content.get("evidence_type") or packet.get("type")
    return str(value) if value else None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None
