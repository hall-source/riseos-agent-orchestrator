# Marketing Workflow Summary View

## Purpose

This endpoint is the first read-only Marketing Mission Control view for the mock Weekly Marketing Command Brief flow.

It turns raw Agent Bus work items and evidence packet IDs into one operational summary so Hall can see what exists, what is missing, and what should happen next without manually reading the raw Agent Bus snapshot.

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
  "status": "ready_for_review",
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
    "status": "queued",
    "evidence_count": 0,
    "ready": false
  },
  "synthesis": {
    "agent_id": "clone-banks-hq",
    "work_item_id": "00000000-0000-0000-0000-000000000000",
    "status": "queued",
    "ready": false
  },
  "readiness": {
    "specialist_evidence_complete": true,
    "review_complete": false,
    "synthesis_complete": false,
    "human_approval_ready": false
  },
  "missing": ["review_packet", "hq_synthesis_packet", "human_approval"],
  "next_action": "Run marketing reviewer or complete mock review packet.",
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

## Marketing Mission Control Support

This gives Marketing Mission Control a stable backend summary before any frontend exists. It provides enough shape for a run card:

- workflow metadata
- per-agent status
- specialist evidence completeness
- reviewer readiness
- HQ synthesis readiness
- missing operational pieces
- next action
- raw snapshot links

## Known Limitations

- The endpoint is read-only and does not execute agents.
- The current mock run creates specialist evidence packets only.
- Review completion is inferred from review work-item status or `metadata.review_packet_ids`.
- HQ synthesis completion is inferred from synthesis work-item status or `metadata.hq_synthesis_packet_ids` / `metadata.synthesis_packet_ids`.
- Human approval is inferred from `metadata.human_approval_status` or `metadata.human_approval`.
- No live marketing source data is connected.

## Recommended Next PR

Create canonical mock review and HQ synthesis packet records so this summary can display real reviewer/HQ artifacts instead of inferred readiness metadata.
