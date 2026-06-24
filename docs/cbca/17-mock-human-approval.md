# Mock Human Approval

## Why This Exists

The mock marketing governance chain can now produce specialist evidence, a reviewer `risk_review`, and a Clone Banks HQ `synthesis_memo`.

The mock human approval action adds the final durable decision layer:

```text
summary reviewed
-> Hall or Marcus approves, rejects, or requests changes
-> human_approval artifact is stored
-> summary shows the decision
-> no production action is triggered
```

## Endpoints

Record a decision:

```http
POST /api/v1/marketing/workflows/{workflow_id}/approval
```

Read the current decision:

```http
GET /api/v1/marketing/workflows/{workflow_id}/approval
```

Both endpoints use the existing orchestrator admin auth pattern. The POST endpoint is disabled unless:

```bash
ENABLE_MARKETING_APPROVAL_MOCK=true
```

## Decisions And States

The POST body accepts:

| Request decision | Stored approval state |
|---|---|
| `approve_mock` | `approved_mock_only` |
| `reject_mock` | `rejected_mock_only` |
| `request_changes` | `changes_requested_mock_only` |

Example:

```json
{
  "decision": "approve_mock",
  "approved_by": "Hall",
  "notes": "Mock synthesis reviewed. Safe to proceed to the next development step.",
  "artifact_id": "synthesis_memo_packet_id"
}
```

`artifact_id` is optional. When supplied, it must match the workflow's `synthesis_memo` artifact id.

## Approval Prerequisites

The POST endpoint refuses to record approval unless the workflow has:

- completed specialist evidence for each required marketing specialist
- a `risk_review` artifact from `hall-marketing-reviewer`
- a `synthesis_memo` artifact from `clone-banks-hq`

This prevents a human decision from being stored before governance has completed.

## Human Approval Artifact

The approval is stored as an Agent Bus evidence packet attached to the Clone Banks HQ synthesis work item.

Artifact shape:

```json
{
  "artifact_type": "human_approval",
  "workflow_id": "...",
  "decision": "approve_mock",
  "approval_state": "approved_mock_only",
  "approved_by": "Hall",
  "notes": "Mock synthesis reviewed. Safe to proceed to the next development step.",
  "approved_artifact_id": "...",
  "approved_artifact_type": "synthesis_memo",
  "mock_mode": true,
  "confidence": "mock_only",
  "live_platform_access": false,
  "no_production_write_performed": true,
  "no_external_platform_action_performed": true,
  "not_for_real_marketing_decisions": true,
  "created_at": "..."
}
```

No Agent Bus approval-specific model was changed for this PR. Evidence packets remain the durable artifact carrier, consistent with the existing governance mock packets.

## GET Response

When no approval exists:

```json
{
  "workflow_id": "...",
  "approval_state": "not_approved",
  "next_action": "Hall can review the mock HQ synthesis memo."
}
```

After approval:

```json
{
  "workflow_id": "...",
  "approval_state": "approved_mock_only",
  "approval_artifact_id": "...",
  "approved_by": "Hall",
  "decision": "approve_mock",
  "notes": "...",
  "mock_mode": true,
  "no_production_write_performed": true,
  "created_at": "..."
}
```

## Summary Behavior

The workflow summary includes:

```json
{
  "human_approval": {
    "state": "approved_mock_only",
    "artifact_id": "...",
    "approved_by": "Hall",
    "decision": "approve_mock",
    "no_production_write_performed": true
  },
  "readiness": {
    "human_approval_ready": true,
    "human_approval_complete": true
  },
  "next_action": "Mock workflow approved. No production action was performed. Next development step can begin."
}
```

Rejected workflows return:

```text
Mock workflow rejected. Review notes and revise the workflow.
```

Change-requested workflows return:

```text
Changes requested. Update the synthesis/governance logic before proceeding.
```

## Safety Guarantees

This feature only records the decision in Agent Bus state. It does not:

- connect live marketing platforms
- call OpenAI
- call ChatGPT agents
- write to Slack, Monday, Drive, Google Ads, HubSpot, GA4, or Search Console
- approve production action
- trigger production execution

Every approval artifact includes:

```json
{
  "mock_mode": true,
  "confidence": "mock_only",
  "live_platform_access": false,
  "no_production_write_performed": true,
  "no_external_platform_action_performed": true,
  "not_for_real_marketing_decisions": true
}
```

## Validation Flow

Create workflow, run worker, run governance, then review summary.

Approve mock synthesis:

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

Read approval:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/approval \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Confirm summary updated:

```bash
curl -sS http://127.0.0.1:8055/api/v1/marketing/workflows/$WORKFLOW_ID/summary \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Remaining Before Real Data Or Real Agents

Before using real data or real agent execution, the system still needs:

- read-only data-source adapters with explicit safe flags
- source-level audit logging
- durable approval records for real-data runs, distinct from mock approvals
- strict no-write tests for each platform
- production write gates that require explicit approval records
- worker scheduling, retries, and failure handling
