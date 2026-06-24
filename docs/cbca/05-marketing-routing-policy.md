# Marketing Routing Policy

## Purpose

The routing policy decides which marketing work items are created, which agent owns each item, which reviewer receives the review item, and when Clone Banks HQ receives the synthesis item.

The first MVP should be deterministic and mock-only.

## Default Weekly Command Brief Fan-Out

| Step | Work item title | Owner agent | Review agent | Output kind |
|---:|---|---|---|---|
| 1 | `RISE Weekly Marketing Data Intelligence` | `hall-data-intelligence` | `hall-marketing-reviewer` | `data_evidence` |
| 2 | `RISE Weekly PPC Intelligence` | `hall-ppc-intelligence` | `hall-marketing-reviewer` | `ppc_evidence` |
| 3 | `RISE Weekly SEO Intelligence` | `hall-seo-intelligence` | `hall-marketing-reviewer` | `seo_evidence` |
| 4 | `RISE Weekly Creative Strategy` | `hall-creative-strategist` | `hall-marketing-reviewer` | `creative_evidence` |
| 5 | `RISE Weekly Marketing Review` | `hall-marketing-reviewer` | `clone-banks-hq` | `review_summary` |
| 6 | `RISE Weekly Clone Banks HQ Command Brief` | `clone-banks-hq` | `hall-marketing-reviewer` | `executive_synthesis` |

## Routing Metadata

Every work item in the workflow should include the shared metadata contract plus role-specific metadata.

```json
{
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "workflow_type": "weekly_marketing_command_brief",
  "source_event": "manual_request",
  "approval_required": true,
  "human_owner": "Hall",
  "review_agent": "hall-marketing-reviewer",
  "workflow_run_id": "uuid",
  "workflow_step": "specialist_data",
  "output_kind": "data_evidence",
  "mvp_mode": "mock_only",
  "live_platform_access": false
}
```

## Status Policy

| Work item kind | Initial status | Mock MVP terminal status | Notes |
|---|---|---|---|
| Specialist item | `queued` | `ready_for_review` or `completed` after evidence attachment | Prefer `ready_for_review` if reviewer item depends on it |
| Reviewer item | `queued` | `ready_for_review` or `approved` | Should summarize all specialist evidence |
| HQ synthesis item | `queued` | `completed` | Represents final command brief artifact/state, not live publishing |

## Human Approval Policy

`approval_required` must be `true` for the MVP. The reviewer and HQ synthesis item can prepare recommendations, but they do not authorize live changes or publication.

## Routing Rules

1. Manual weekly command brief requests create exactly one workflow run ID.
2. Each specialist item uses the same workflow run ID and correlation ID family.
3. Specialist items are independent for the MVP.
4. The reviewer item depends on all specialist item IDs.
5. The HQ synthesis item depends on the reviewer item and all specialist items.
6. No item can claim live platform access in metadata during the first PR.
7. Any future live integration must add explicit read-only/write capability flags and approval gates.

## Existing Endpoint Option

`POST /api/v1/agent-tasks` can accept a generic task, but it does not express fan-out routing. Use it only if Hall wants zero new endpoints. Otherwise, add a marketing-specific endpoint so routing remains obvious.

## Recommended New Endpoint

```text
POST /api/v1/marketing/weekly-command-brief/mock-run
```

Recommended request body:

```json
{
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "human_owner": "Hall",
  "requested_by": "Marcus",
  "period_start": "2026-06-17",
  "period_end": "2026-06-24"
}
```

Recommended response body:

```json
{
  "accepted": true,
  "workflow_run_id": "uuid",
  "agent_seed_results": [],
  "specialist_work_items": [],
  "reviewer_work_item": {},
  "synthesis_work_item": {},
  "mission_control_url": "http://127.0.0.1:8001/api/v1/mission-control/snapshot"
}
```
