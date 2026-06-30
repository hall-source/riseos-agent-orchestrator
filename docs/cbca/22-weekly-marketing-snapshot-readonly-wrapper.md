# Weekly Marketing Snapshot Read-Only Wrapper

## Purpose

This endpoint wraps the validated manual Clone Banks weekly marketing snapshot flow into one safe command.

It creates a mock weekly marketing workflow, attaches approved Google Sheets read-only analytics evidence, optionally runs the mock specialist worker, optionally runs mock governance, and then stops before human approval.

This is still mock-only except for the read-only Google Sheets evidence source.

## Endpoint

```http
POST /api/v1/marketing/workflows/weekly-snapshot/read-only/run
```

The endpoint is admin-protected and requires:

```bash
ENABLE_WEEKLY_MARKETING_SNAPSHOT_READONLY=true
```

## Request Body

```json
{
  "business_unit": "RISE Commercial District",
  "requested_by": "Hall",
  "date_range_label": "last_7_days",
  "source_type": "google_sheet",
  "source_id": "1iJSBcqdOAlfFCFTOD_bpNoP0iDr3KNZfNnXgKO-Ewkw",
  "sheet_name": "Weekly Marketing Snapshot",
  "run_mock_workers": true,
  "run_mock_governance": true
}
```

Only `source_type=google_sheet` is supported by the wrapper.

## Response Shape

```json
{
  "workflow_id": "...",
  "created_work_items": [],
  "data_work_item_id": "...",
  "analytics_evidence_packet_id": "...",
  "worker_run_id": "...",
  "governance_run_id": "...",
  "review_artifact_id": "...",
  "synthesis_artifact_id": "...",
  "audit_events_url": "/api/v1/marketing/evidence/audit?workflow_id=...",
  "summary_url": "/api/v1/marketing/workflows/.../summary",
  "approval_required": true,
  "human_approval_performed": false,
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "next_action": "Hall must review the synthesis and call the approval endpoint manually. No production action has been authorized."
}
```

## Required Flags

```bash
ENABLE_WEEKLY_MARKETING_SNAPSHOT_READONLY=true
ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true
ENABLE_MARKETING_WORKER_MOCK=true
ENABLE_MARKETING_GOVERNANCE_MOCK=true
ENABLE_MARKETING_APPROVAL_MOCK=true
GOOGLE_APPLICATION_CREDENTIALS=/etc/clone-banks/secrets/google-sheets-readonly-service-account.json
MARKETING_READONLY_ALLOWED_SOURCE_IDS=1iJSBcqdOAlfFCFTOD_bpNoP0iDr3KNZfNnXgKO-Ewkw
```

`ENABLE_MARKETING_WORKER_MOCK=true` is required only when `run_mock_workers=true`.

`ENABLE_MARKETING_GOVERNANCE_MOCK=true` is required only when `run_mock_governance=true`.

## Workflow Steps

The wrapper performs these steps:

1. Checks `ENABLE_WEEKLY_MARKETING_SNAPSHOT_READONLY=true`.
2. Preflights optional worker/governance flags.
3. Creates a weekly marketing command brief workflow with `auto_complete_specialists=false`.
4. Finds the `hall-data-intelligence` specialist work item.
5. Attaches Google Sheets read-only evidence through the existing approved adapter.
6. Records the existing read-only evidence audit event.
7. Runs mock workers when requested.
8. Runs mock governance when requested.
9. Returns summary and audit URLs.
10. Stops before human approval.

## Manual Approval Requirement

The wrapper does not approve the workflow.

Hall must review the synthesis and make a separate explicit approval call:

```http
POST /api/v1/marketing/workflows/{workflow_id}/approval
```

This guardrail is intentional. No production action is authorized by the wrapper.

## Safety Model

This endpoint does not:

- write to Google Sheets
- write to Google Ads
- write to Meta
- write to HubSpot
- write to Slack
- write to Monday
- call OpenAI or ChatGPT agents
- trigger live platform actions
- approve itself
- use broad Google Drive access
- bypass source allowlisting
- bypass admin auth

The response always reports:

```json
{
  "approval_required": true,
  "human_approval_performed": false,
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true
}
```

## Server Validation

After deployment:

```bash
curl -sS -X POST "$ORCHESTRATOR_BASE/api/v1/marketing/workflows/weekly-snapshot/read-only/run" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "business_unit": "RISE Commercial District",
    "requested_by": "Hall",
    "date_range_label": "last_7_days",
    "source_type": "google_sheet",
    "source_id": "1iJSBcqdOAlfFCFTOD_bpNoP0iDr3KNZfNnXgKO-Ewkw",
    "sheet_name": "Weekly Marketing Snapshot",
    "run_mock_workers": true,
    "run_mock_governance": true
  }' | jq .
```

Expected result:

- workflow created
- Google Sheets evidence attached
- mock specialist workers complete
- mock reviewer complete
- mock HQ synthesis complete
- human approval not performed
- response includes summary URL and audit URL
- no production writes
- no external platform actions
- manual approval remains required

Read summary:

```bash
curl -sS "$ORCHESTRATOR_BASE/api/v1/marketing/workflows/$WORKFLOW_ID/summary" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Read audit events:

```bash
curl -sS "$ORCHESTRATOR_BASE/api/v1/marketing/evidence/audit?workflow_id=$WORKFLOW_ID" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Known Limits

- The wrapper supports only the approved Google Sheets read-only evidence path.
- Human approval remains a separate explicit endpoint call.
- The wrapper does not add Drive CSV, Google Ads, HubSpot, GA4, Search Console, Slack, Monday, OpenAI, or ChatGPT agent execution.
