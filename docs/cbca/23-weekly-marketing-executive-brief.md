# Weekly Marketing Executive Brief

## Purpose

The weekly marketing executive brief endpoint turns an existing governed Weekly Marketing Snapshot workflow into a structured JSON brief Hall can review.

It is a read-only reporting endpoint over already-created workflow data. It does not run agents, call OpenAI, call ChatGPT, approve workflows, write to external systems, or mutate Agent Bus state.

The brief is deterministic and template-based. It is not LLM-generated narrative.

## Endpoint

```http
GET /api/v1/marketing/workflows/{workflow_id}/executive-brief
```

The endpoint requires orchestrator admin auth and this feature flag:

```bash
ENABLE_WEEKLY_MARKETING_EXECUTIVE_BRIEF=true
```

## Response Example

```json
{
  "workflow_id": "marketing-wf-...",
  "brief_type": "weekly_marketing_executive_brief",
  "business_unit": "RISE Commercial District",
  "date_range_label": "last_7_days",
  "status": "awaiting_human_approval",
  "approval_state": "not_approved",
  "approval_required": true,
  "human_approval_complete": false,
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true,
  "executive_summary": {
    "headline": "Weekly marketing snapshot is ready for review.",
    "summary": "Read-only marketing evidence was collected and synthesized. Human approval is still required before any production action."
  },
  "scorecard": {
    "leads": 42,
    "contacts_created": 38,
    "deals_created": 6,
    "sessions": 1200,
    "deal_created_rate_from_leads": 0.1429
  },
  "channel_breakdown": [
    {
      "source": "paid_search",
      "leads": 18,
      "contacts_created": 16,
      "deals_created": 3,
      "sessions": 450
    }
  ],
  "findings": [
    "Read-only source reported 42 leads and 6 deals created.",
    "Deal-created rate from leads is 0.1429."
  ],
  "review": {
    "ready": true,
    "artifact_id": "...",
    "risk_flags": [],
    "approval_recommendation": "ready_for_hq_synthesis_mock_only"
  },
  "synthesis": {
    "ready": true,
    "artifact_id": "...",
    "summary": "..."
  },
  "recommended_next_action": "Hall should review the synthesis and approve or request changes.",
  "links": {
    "summary_url": "/api/v1/marketing/workflows/marketing-wf-.../summary",
    "audit_events_url": "/api/v1/marketing/evidence/audit?workflow_id=marketing-wf-...",
    "approval_url": "/api/v1/marketing/workflows/marketing-wf-.../approval"
  }
}
```

## How It Works

The route validates admin auth and `ENABLE_WEEKLY_MARKETING_EXECUTIVE_BRIEF`, loads the existing marketing workflow summary, and passes that already-loaded data to `app/marketing_executive_brief_builder.py`.

The builder deterministically projects the workflow summary into an executive brief. Keeping the transformation in a dedicated builder makes the same leadership brief logic reusable later for PDF generation, Google Doc generation, Slack summaries, email digests, future LLM narrative overlays, and internal saved artifacts without putting presentation logic in the route handler.

It extracts:

- the canonical `analytics_snapshot` evidence, preferring `source_mode=google_sheets_readonly`
- scorecard metrics
- channel/source breakdown
- findings from analytics evidence
- reviewer risk flags and approval recommendation
- Clone Banks HQ synthesis summary
- human approval state

If analytics evidence is missing, the endpoint returns a controlled partial brief with an empty scorecard and a finding that analytics evidence is not available.

## Approval State Behavior

Before manual approval:

```json
{
  "status": "awaiting_human_approval",
  "approval_state": "not_approved",
  "human_approval_complete": false,
  "recommended_next_action": "Hall should review the synthesis and approve or request changes."
}
```

After explicit manual approval:

```json
{
  "status": "completed",
  "approval_state": "approved_mock_only",
  "human_approval_complete": true,
  "recommended_next_action": "Mock workflow has been validated. No production action has been authorized."
}
```

The executive brief endpoint does not approve workflows. Human approval remains a separate explicit call:

```http
POST /api/v1/marketing/workflows/{workflow_id}/approval
```

## Safety Model

This endpoint and builder do not:

- call OpenAI or ChatGPT
- call Google Ads
- call Meta
- call HubSpot
- call Slack
- call Monday
- write to Google Sheets
- write to Google Drive
- create PDFs, Google Docs, Slack messages, emails, Monday items, or presentations
- perform production actions
- approve the workflow
- mutate workflow state
- bypass admin auth
- bypass existing workflow/evidence/review/synthesis logic

The response always reports:

```json
{
  "live_platform_access": false,
  "write_access": false,
  "not_for_real_marketing_decisions": true
}
```

## Validation Commands

Run the existing wrapper endpoint:

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

Call the executive brief before approval:

```bash
curl -sS "$ORCHESTRATOR_BASE/api/v1/marketing/workflows/$NEW_WORKFLOW_ID/executive-brief" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Expected:

- `approval_state=not_approved`
- `human_approval_complete=false`
- scorecard metrics present
- no write/live-platform flags true

Manually approve:

```bash
curl -sS -X POST "$ORCHESTRATOR_BASE/api/v1/marketing/workflows/$NEW_WORKFLOW_ID/approval" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision":"approve_mock","approved_by":"Hall","notes":"Executive brief endpoint validated. No production action authorized."}' | jq .
```

Call the executive brief again:

```bash
curl -sS "$ORCHESTRATOR_BASE/api/v1/marketing/workflows/$NEW_WORKFLOW_ID/executive-brief" \
  -H "Authorization: Bearer $ORCHESTRATOR_ADMIN_TOKEN" | jq .
```

Expected:

- `approval_state=approved_mock_only`
- `human_approval_complete=true`
- `status=completed`
- no production action authorized

## Known Limitations

- The brief is deterministic/template-based.
- No LLM-generated narrative is used yet.
- The endpoint returns JSON only.
- Durable `executive_weekly_marketing_brief` artifact persistence is intentionally deferred.