# Marketing Governance Stage Runner

## Why This Exists

The worker adapter proves that specialist marketing work can be claimed and completed after the orchestrator creates mock Agent Bus work items.

The governance stage runner proves the next boundary:

```text
worker-produced specialist evidence
-> hall-marketing-reviewer risk review
-> clone-banks-hq synthesis memo
-> human approval readiness
```

This keeps governance execution separate from the original mock-run endpoint and closer to the future live workflow shape.

## Endpoint

```http
POST /api/v1/marketing/governance/mock/run-once
```

The endpoint is admin-protected and disabled unless:

```bash
ENABLE_MARKETING_GOVERNANCE_MOCK=true
```

Request:

```json
{
  "workflow_id": "marketing-wf-...",
  "run_reviewer": true,
  "run_hq_synthesis": true
}
```

Response:

```json
{
  "governance_run_id": "marketing-governance-run-...",
  "workflow_id": "marketing-wf-...",
  "reviewer_result": {
    "status": "completed",
    "work_item_id": "...",
    "artifact_id": "...",
    "artifact_type": "risk_review"
  },
  "hq_result": {
    "status": "completed",
    "work_item_id": "...",
    "artifact_id": "...",
    "artifact_type": "synthesis_memo"
  },
  "mock_mode": true,
  "live_platform_access": false,
  "next_action": "Hall can review the mock HQ synthesis memo. No production action is allowed from mock evidence."
}
```

## Runner Behavior

The runner:

- accepts one `workflow_id`
- lists Agent Bus work items for the marketing repository
- verifies all required specialist work items exist
- verifies every required specialist item has at least one evidence packet
- verifies specialist evidence is mock-only and has `live_platform_access=false`
- creates the `hall-marketing-reviewer` work item if missing
- attaches a `risk_review` evidence artifact to the reviewer item
- creates the `clone-banks-hq` work item if missing
- attaches a `synthesis_memo` evidence artifact to the HQ item
- marks reviewer/HQ work complete when the current Agent Bus lifecycle supports completion

If specialist evidence is missing, it refuses the governance run and tells the caller to run the specialist worker first.

## Review Artifact

The reviewer artifact is stored as an evidence packet with:

```json
{
  "artifact_type": "risk_review",
  "produced_by": "hall-marketing-reviewer",
  "workflow_type": "weekly_marketing_command_brief",
  "workflow_id": "...",
  "referenced_evidence_packet_ids": [],
  "approval_recommendation": "ready_for_hq_synthesis_mock_only",
  "mock_mode": true,
  "confidence": "mock_only",
  "live_platform_access": false,
  "not_for_real_marketing_decisions": true,
  "human_approval_required": true
}
```

The `referenced_evidence_packet_ids` list is populated from the actual specialist evidence packets attached to the workflow's specialist work items.

## HQ Synthesis Artifact

The HQ artifact is stored as an evidence packet with:

```json
{
  "artifact_type": "synthesis_memo",
  "produced_by": "clone-banks-hq",
  "workflow_type": "weekly_marketing_command_brief",
  "workflow_id": "...",
  "referenced_evidence_packet_ids": [],
  "referenced_review_artifact_id": "...",
  "approval_status": "awaiting_human_approval_mock_only",
  "mock_mode": true,
  "confidence": "mock_only",
  "live_platform_access": false,
  "not_for_real_marketing_decisions": true,
  "human_approval_required": true
}
```

The memo references both the specialist evidence IDs and the reviewer artifact ID.

## Human Approval Handoff

After governance runs, the summary should show `human_approval_ready=true` and `human_approval_complete=false` until Hall or Marcus records a decision.

The next step is handled by:

```http
POST /api/v1/marketing/workflows/{workflow_id}/approval
```

That endpoint records a `human_approval` evidence artifact on the HQ synthesis work item. It does not trigger production action.

## Summary Readiness

The summary endpoint still reads Agent Bus work items and attached evidence packets as the source of truth.

Readiness becomes:

- `specialist_evidence_complete=true` when each specialist work item has evidence
- `review_complete=true` when the reviewer item has a `risk_review` artifact
- `synthesis_complete=true` when the HQ item has a `synthesis_memo` artifact
- `human_approval_ready=true` when all three are complete
- `human_approval_complete=true` when a `human_approval` artifact exists

Next action guidance now reflects the staged flow:

- missing specialist evidence: `Run the specialist worker before governance.`
- review complete but HQ missing: `Run HQ synthesis.`
- review and synthesis complete: Hall can review the mock HQ synthesis memo
- approved: mock workflow approved; no production action was performed
- rejected: review notes and revise the workflow
- changes requested: update the synthesis/governance logic before proceeding

## Safety Boundaries

This runner does not:

- connect live Google Ads, HubSpot, GA4, Search Console, Slack, Monday, or Drive
- call OpenAI
- call ChatGPT agents
- execute real marketing agents
- approve production actions
- write to production systems

Every generated governance artifact repeats the mock safeguards:

```json
{
  "mock_mode": true,
  "confidence": "mock_only",
  "live_platform_access": false,
  "not_for_real_marketing_decisions": true,
  "human_approval_required": true
}
```

The follow-on human approval artifact additionally records:

```json
{
  "no_production_write_performed": true,
  "no_external_platform_action_performed": true
}
```

## Validation Flow

Create a workflow without pre-generated specialist evidence:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/weekly-command-brief/mock-run \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit":"RISE Commercial District",
    "requested_by":"Hall",
    "date_range_label":"mock_last_7_days",
    "auto_complete_specialists": false
  }' | jq .
```

Run the specialist worker:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workers/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id":"'$WORKFLOW_ID'",
    "max_items":4
  }' | jq .
```

Run governance:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/governance/mock/run-once \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id":"'$WORKFLOW_ID'",
    "run_reviewer": true,
    "run_hq_synthesis": true
  }' | jq .
```

Record human approval:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve_mock",
    "approved_by": "Hall",
    "notes": "Mock synthesis reviewed. Safe to proceed to the next development step."
  }' | jq .
```

Read the summary:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Verify Agent Bus:

```bash
curl -sS http://127.0.0.1:8050/api/v1/mission-control/snapshot | jq .
```

## Remaining Before Real Agent Execution

Before real reviewer, HQ, or specialist execution can run, the system still needs:

- read-only source adapters with per-source safe flags
- audit logs for every external source read
- explicit no-write tests for each marketing platform
- production action gates with approval records
- worker scheduling and retry policy
