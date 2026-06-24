# Marketing Workflow Summary View

## Purpose

This endpoint is the read-only Marketing Mission Control view for the mock Weekly Marketing Command Brief flow.

It turns raw Agent Bus work items, review packet references, and evidence packet IDs into one operational summary so Hall can see what exists, what is missing, and what should happen next without manually reading the raw Agent Bus snapshot.

## Endpoint

```http
GET /api/v1/marketing/workflows/{workflow_id}/summary
```

## Required Auth

Use either admin auth pattern:

```text
Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN
```

or:

```text
X-Orchestrator-Admin-Token: $ORCHESTRATOR_ADMIN_TOKEN
```

## Example Request

Create a mock workflow first:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"business_unit":"RISE Commercial District","requested_by":"Hall","date_range_label":"mock_last_7_days"}' | jq .
```

Copy the returned `workflow_id`, then request the summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Example Response

```json
{
  "workflow_id": "marketing-wf-00000000-0000-0000-0000-000000000000",
  "workflow_type": "weekly_marketing_command_brief",
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "source_event": "manual_mock_request",
  "status": "awaiting_human_approval",
  "requested_by": "Hall",
  "human_owner": "Hall",
  "approval_required": true,
  "created_at": "2026-06-24T18:00:00+00:00",
  "updated_at": "2026-06-24T18:00:00+00:00",
  "agents": [
    {
      "agent_id": "hall-data-intelligence",
      "role": "specialist",
      "status": "completed",
      "work_item_id": "00000000-0000-0000-0000-000000000000",
      "evidence_count": 1,
      "evidence_types": ["analytics_snapshot"]
    }
  ],
  "specialist_work_items": [],
  "evidence_packets": [],
  "review": {
    "review_agent": "hall-marketing-reviewer",
    "work_item_id": "00000000-0000-0000-0000-000000000000",
    "status": "completed",
    "artifact_type": "risk_review",
    "artifact_id": "00000000-0000-0000-0000-000000000000",
    "review_packet_ids": ["00000000-0000-0000-0000-000000000000"],
    "approval_recommendation": "ready_for_hq_synthesis_mock_only",
    "risk_flags": [
      "mock_only_no_business_decisions",
      "requires_real_data_before_operational_use"
    ],
    "evidence_count": 1,
    "ready": true
  },
  "synthesis": {
    "agent_id": "clone-banks-hq",
    "work_item_id": "00000000-0000-0000-0000-000000000000",
    "status": "completed",
    "artifact_type": "synthesis_memo",
    "artifact_id": "00000000-0000-0000-0000-000000000000",
    "approval_status": "awaiting_human_approval_mock_only",
    "summary": "Mock Weekly Marketing Command Brief synthesized from specialist mock evidence and mock reviewer packet.",
    "ready": true
  },
  "readiness": {
    "specialist_evidence_complete": true,
    "review_complete": true,
    "synthesis_complete": true,
    "human_approval_ready": true
  },
  "missing": [],
  "next_action": "Hall can review the mock HQ synthesis memo. No production action is allowed from mock evidence.",
  "links": {
    "agent_bus_mission_control": "http://127.0.0.1:8050/api/v1/mission-control/snapshot",
    "orchestrator_snapshot": "http://127.0.0.1:8055/api/v1/orchestrator/snapshot"
  }
}
```

## How The Join Works

The endpoint asks Agent Bus for work items in `hall-source/riseos-agent-orchestrator`, then filters them by:

```text
metadata.workflow_id == {workflow_id}
```

It identifies item roles from `metadata.work_item_role`:

- `specialist_evidence`
- `marketing_review`
- `hq_synthesis`

It fetches canonical evidence packet details from each work item's `metadata.evidence_packet_ids`.

The reviewer summary is populated from the attached evidence packet whose `test_results.artifact_type` or `test_results.evidence_type` is `risk_review`. The canonical Agent Bus review packet id is exposed from the reviewer work item's `metadata.review_packet_ids`.

The HQ synthesis summary is populated from the attached evidence packet whose `test_results.artifact_type` or `test_results.evidence_type` is `synthesis_memo`.

## Readiness Calculation

The summary sets readiness flags as follows:

- `specialist_evidence_complete`: every specialist work item exists and has at least one evidence packet
- `review_complete`: reviewer work item has an attached `risk_review` artifact, or a legacy review packet reference exists
- `synthesis_complete`: HQ work item has an attached `synthesis_memo` artifact, or a legacy synthesis packet reference exists
- `human_approval_ready`: specialist evidence, review, and synthesis are complete, approval is required, and human approval has not yet been recorded

When `human_approval_ready=true`, `missing` is empty because the system has everything needed for Hall to review. It does not mean approval has already happened.

## Marketing Mission Control Support

This gives Marketing Mission Control a stable backend summary before any frontend exists. It provides enough shape for a run card:

- workflow metadata
- per-agent status
- specialist evidence completeness
- reviewer artifact and risk flags
- HQ synthesis memo status and summary
- human approval readiness
- missing operational pieces
- next action
- raw snapshot links

## Known Limitations

- The endpoint is read-only and does not execute agents.
- Review and synthesis artifacts are generated by mock logic during the mock run.
- The richer risk review is stored as an evidence artifact because the canonical Agent Bus review packet model is intentionally lifecycle-focused.
- Human approval readiness is visible, but durable approval action is not implemented yet.
- No live marketing source data is connected.

## Recommended Next PR

Add a Marketing Agent Worker Adapter contract that can replace mock artifact generation with controlled worker execution while keeping live integrations disabled until approval boundaries are tested.
