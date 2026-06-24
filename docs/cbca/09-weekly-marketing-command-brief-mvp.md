# Weekly Marketing Command Brief MVP

## Goal

Create a mock-only weekly marketing command brief workflow that proves the orchestration loop without connecting live platforms.

The MVP should demonstrate that the Orchestrator can start a marketing workflow, use Agent Bus as the canonical ledger, attach evidence, create a reviewer item, create a Clone Banks HQ synthesis item, and make the final state visible through Mission Control.

## MVP Loop

```text
manual marketing command brief request
-> orchestrator creates mock/simulated specialist work items
-> Agent Bus stores work items
-> fake worker/evidence function attaches evidence packets
-> reviewer work item is created
-> Clone Banks HQ synthesis item is created
-> final state is visible through mission-control/snapshot
```

## Request Model

Recommended endpoint:

```text
POST /api/v1/marketing/weekly-command-brief/mock-run
```

Recommended request:

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

## Response Model

```json
{
  "accepted": true,
  "mode": "mock_only",
  "workflow_run_id": "uuid",
  "metadata": {
    "domain": "marketing",
    "brand": "rise",
    "business_unit": "RISE Commercial District",
    "workflow_type": "weekly_marketing_command_brief",
    "source_event": "manual_request",
    "approval_required": true,
    "human_owner": "Hall",
    "review_agent": "hall-marketing-reviewer"
  },
  "agent_seed_results": [
    {"agent_id": "clone-banks-hq", "status": "registered_or_existing"}
  ],
  "specialist_work_items": [
    {"agent_id": "hall-data-intelligence", "work_item_id": "uuid", "evidence_packet_id": "uuid"}
  ],
  "reviewer_work_item": {"work_item_id": "uuid", "agent_id": "hall-marketing-reviewer"},
  "synthesis_work_item": {"work_item_id": "uuid", "agent_id": "clone-banks-hq"},
  "mission_control_url": "http://127.0.0.1:8001/api/v1/mission-control/snapshot"
}
```

## Specialist Work Items

| Agent | Title | Mock output |
|---|---|---|
| `hall-data-intelligence` | `RISE Weekly Marketing Data Intelligence` | KPI posture, measurement caveat, data-quality notes |
| `hall-ppc-intelligence` | `RISE Weekly PPC Intelligence` | Paid media posture, spend caveat, paid-search recommendation |
| `hall-seo-intelligence` | `RISE Weekly SEO Intelligence` | Organic opportunity, content gap, search-intent caveat |
| `hall-creative-strategist` | `RISE Weekly Creative Strategy` | Offer angle, creative test, messaging caveat |

## Reviewer Work Item

The reviewer item should be assigned to `hall-marketing-reviewer` and depend on all specialist work item IDs.

Suggested title:

```text
RISE Weekly Marketing Review
```

Suggested reviewer evidence summary:

```text
Reviewed four mock specialist evidence packets. No live platform data was used. Recommendations are planning-only and require Hall approval before execution.
```

## Clone Banks HQ Synthesis Item

The synthesis item should be assigned to `clone-banks-hq` and depend on all specialist item IDs plus the reviewer item ID.

Suggested title:

```text
RISE Weekly Clone Banks HQ Command Brief
```

Suggested output sections:

- Situation.
- Channel intelligence.
- Recommended priorities.
- Approval needed.
- Unverified or mock-only items.

## Mission Control Acceptance Criteria

After running the endpoint, `GET /api/v1/mission-control/snapshot` should show:

- Six marketing agents registered or visible.
- At least six work items connected to the run.
- Evidence packet count increased.
- Review count or reviewer work item visible.
- Queue counts changed from empty baseline.

## MVP Non-Goals

- No live data import.
- No live platform write.
- No scheduling.
- No Slack/Monday notification.
- No UI build.
- No schema migration unless Agent Bus evidence APIs require it.
