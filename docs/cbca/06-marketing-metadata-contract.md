# Marketing Metadata Contract

## Required Base Metadata

All Marketing Agent Loop MVP work items must include this base metadata.

```json
{
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "workflow_type": "weekly_marketing_command_brief",
  "source_event": "manual_request",
  "approval_required": true,
  "human_owner": "Hall",
  "review_agent": "hall-marketing-reviewer"
}
```

## Recommended Full MVP Metadata

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
  "requested_by": "Marcus",
  "period_start": "2026-06-17",
  "period_end": "2026-06-24",
  "workflow_step": "specialist_data",
  "output_kind": "data_evidence",
  "parent_work_item_id": null,
  "depends_on_work_item_ids": [],
  "mvp_mode": "mock_only",
  "live_platform_access": false,
  "approval_state": "not_requested"
}
```

## Field Definitions

| Field | Required | Type | Notes |
|---|---:|---|---|
| `domain` | Yes | string | Must be `marketing` for this workflow |
| `brand` | Yes | string | Must be `rise` for the first MVP |
| `business_unit` | Yes | string | Use `RISE Commercial District` |
| `workflow_type` | Yes | string | Must be `weekly_marketing_command_brief` |
| `source_event` | Yes | string | Must be `manual_request` for MVP |
| `approval_required` | Yes | boolean | Must be `true` |
| `human_owner` | Yes | string | Must be `Hall` unless explicitly changed |
| `review_agent` | Yes | string | Must be `hall-marketing-reviewer` for MVP |
| `workflow_run_id` | Recommended | UUID string | Connects all work items in one run |
| `requested_by` | Recommended | string | Operator who initiated the run |
| `period_start` | Recommended | ISO date | Reporting period start |
| `period_end` | Recommended | ISO date | Reporting period end |
| `workflow_step` | Recommended | string | Step-specific key such as `specialist_ppc` |
| `output_kind` | Recommended | string | Evidence or synthesis output type |
| `parent_work_item_id` | Optional | UUID string or null | Parent item when a hierarchy is useful |
| `depends_on_work_item_ids` | Optional | array | Work item dependencies |
| `mvp_mode` | Recommended | string | Must be `mock_only` for first PR |
| `live_platform_access` | Recommended | boolean | Must be `false` for first PR |
| `approval_state` | Recommended | string | Suggested values: `not_requested`, `pending_human`, `approved`, `rejected` |

## Step Values

| Step | `workflow_step` | `output_kind` |
|---|---|---|
| Data specialist | `specialist_data` | `data_evidence` |
| PPC specialist | `specialist_ppc` | `ppc_evidence` |
| SEO specialist | `specialist_seo` | `seo_evidence` |
| Creative specialist | `specialist_creative` | `creative_evidence` |
| Reviewer | `marketing_review` | `review_summary` |
| Clone Banks HQ synthesis | `hq_synthesis` | `executive_synthesis` |

## Compatibility Notes

Agent Bus `WorkItemCreate` already includes a free-form `metadata` object. The first PR should use that field instead of changing the Agent Bus schema.

If future Mission Control screens need first-class marketing fields, add derived snapshot projection fields later. Do not change the canonical work item schema until the metadata-only approach proves insufficient.

## Validation Rules For First PR

- Reject requests where `brand` is not `rise` unless Hall approves multi-brand routing.
- Reject requests where `approval_required` is false.
- Force `source_event` to `manual_request` from the endpoint implementation.
- Force `mvp_mode` to `mock_only`.
- Force `live_platform_access` to `false`.
- Do not accept arbitrary owner/reviewer IDs unless they match the seed registry.

## Example Specialist Work Item

```json
{
  "title": "RISE Weekly PPC Intelligence",
  "repository": "hall-source/riseos-agent-orchestrator",
  "priority": "normal",
  "owner_agent": "hall-ppc-intelligence",
  "review_agent": "hall-marketing-reviewer",
  "correlation_id": "workflow-run-uuid",
  "metadata": {
    "domain": "marketing",
    "brand": "rise",
    "business_unit": "RISE Commercial District",
    "workflow_type": "weekly_marketing_command_brief",
    "source_event": "manual_request",
    "approval_required": true,
    "human_owner": "Hall",
    "review_agent": "hall-marketing-reviewer",
    "workflow_run_id": "workflow-run-uuid",
    "workflow_step": "specialist_ppc",
    "output_kind": "ppc_evidence",
    "mvp_mode": "mock_only",
    "live_platform_access": false
  }
}
```
