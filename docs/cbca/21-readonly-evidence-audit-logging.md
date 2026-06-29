# Read-Only Evidence Audit Logging

## Purpose

The Google Sheets read-only evidence adapter can now read one approved external source in read-only mode. Before live validation, every attach attempt needs a durable audit trail.

This PR audits calls to:

```http
POST /api/v1/marketing/evidence/google-sheets-readonly/attach
```

The fixture endpoint is not audited in this PR. The priority is the real read-only Google Sheets path.

## What Is Audited

Each audit record includes:

```json
{
  "audit_event_id": "...",
  "event_type": "marketing_readonly_evidence_attach_attempt",
  "workflow_id": "...",
  "work_item_id": "...",
  "agent_id": "hall-data-intelligence",
  "source_type": "google_sheet",
  "source_mode": "google_sheets_readonly",
  "source_id_hash": "...",
  "source_id_last_6": "abc123",
  "sheet_name": "Weekly Marketing Snapshot",
  "date_range_label": "last_7_days",
  "requested_by": "admin_token_authenticated_request",
  "allowlist_passed": true,
  "credentials_present": true,
  "write_access": false,
  "live_platform_access": false,
  "status": "success",
  "failure_reason": null,
  "evidence_packet_id": "...",
  "created_at": "..."
}
```

## What Is Not Logged

Audit records intentionally do not include:

- full Google Sheet source IDs
- credential file contents
- credential file paths
- secret environment variable values
- raw Authorization headers
- admin token values
- Google access tokens

The source ID is stored as a SHA-256 hash plus the last six characters for debugging.

Failure reasons are sanitized so the full source ID is replaced with:

```text
[redacted_source_id]
```

## Storage Behavior

The repository uses a small service abstraction:

```text
app/marketing_evidence_audit.py
app/marketing_evidence_audit_contract.py
```

When `ORCHESTRATOR_DB_PATH` is configured, audit events are appended as JSON lines beside that path:

```text
<ORCHESTRATOR_DB_PATH>.marketing_evidence_audit.jsonl
```

If `ORCHESTRATOR_DB_PATH` is not configured, the app uses an in-memory repository. Tests inject this repository through app state.

## Feature Flag Decision

Audit writes are always on for the Google Sheets read-only evidence endpoint, including failed attempts and feature-flag rejection.

`ENABLE_MARKETING_EVIDENCE_AUDIT` controls only the read endpoint:

```http
GET /api/v1/marketing/evidence/audit
```

The default is enabled. Set it to `false` only if the audit read endpoint must be hidden while preserving writes.

## GET Audit Endpoint

```http
GET /api/v1/marketing/evidence/audit
```

The endpoint is admin-protected and supports optional filters:

```text
workflow_id
source_mode
status
limit
```

Example:

```bash
curl -sS "http://127.0.0.1:8055/api/v1/marketing/evidence/audit?workflow_id=$WORKFLOW_ID" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

## Failure Audit Behavior

Failed audit records are created for:

- `ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE` disabled
- source ID missing
- source ID not allowlisted
- credentials missing
- sheet name missing
- expected columns missing
- no rows matching `date_range_label`
- Google read failure
- unsupported agent
- Agent Bus evidence attach failure

## Safety Guarantees

This audit layer does not:

- add write scopes
- write to Google Sheets or Drive
- broaden Drive or Sheets access
- call Google Ads, HubSpot, GA4, Search Console, Slack, Monday, OpenAI, or ChatGPT agents
- perform production actions

Every audit record stores:

```json
{
  "write_access": false,
  "live_platform_access": false
}
```

## Runtime Validation Flow

After deployment with env vars set:

```bash
curl -sS -X POST http://127.0.0.1:8055/api/v1/marketing/evidence/google-sheets-readonly/attach \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "'$WORKFLOW_ID'",
    "agent_id": "hall-data-intelligence",
    "work_item_id": "'$DATA_WORK_ITEM_ID'",
    "source_type": "google_sheet",
    "source_id": "'$MARKETING_TEST_SHEET_ID'",
    "sheet_name": "Weekly Marketing Snapshot",
    "date_range_label": "last_7_days"
  }' | jq .
```

Then:

```bash
curl -sS "http://127.0.0.1:8055/api/v1/marketing/evidence/audit?workflow_id=$WORKFLOW_ID" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Confirm:

```text
status=success
source_mode=google_sheets_readonly
write_access=false
live_platform_access=false
no credentials logged
no Authorization header logged
```

Also test an allowlist failure and confirm it creates a failed audit event.

## Remaining Limitations

- The workflow summary does not yet include audit counts.
- The fixture endpoint is not audited in this PR.
- JSONL storage is intentionally minimal; if audit volume grows, migrate this repository behind a stronger store.
- Live Sheets validation still remains a separate operational step.
