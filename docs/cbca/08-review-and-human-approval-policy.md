# Review And Human Approval Policy

## Policy Summary

The Marketing Agent Loop may prepare recommendations, evidence packets, and command briefs. It must not publish, spend, modify campaigns, update CRM records, message customers, post to Slack/Monday as an operational action, or change production behavior without human approval.

For the MVP, all outputs are mock-only and planning-only.

## Approval Boundary

| Action | Agent may do in MVP | Requires Hall approval |
|---|---:|---:|
| Create mock specialist work items | Yes | No |
| Create mock evidence packets | Yes | No |
| Create reviewer work item | Yes | No |
| Create Clone Banks HQ synthesis item | Yes | No |
| Recommend campaign or content changes | Yes, as planning output | Before execution |
| Connect live marketing data sources | No | Yes |
| Change Google Ads, HubSpot, GA4, Search Console, Slack, or Monday | No | Yes |
| Spend money or alter budgets | No | Yes |
| Publish customer-facing content | No | Yes |

## Review Agent Role

`hall-marketing-reviewer` is an agent-level review gate, not the final human approver. Its job is to inspect evidence, identify risks, flag assumptions, and prepare a human approval handoff.

It should produce:

- Reviewed specialist work item IDs.
- Reviewed evidence packet IDs.
- Findings.
- Required changes or caveats.
- Risk level.
- Human approval checklist.
- Items that must remain blocked.

## Human Owner

The metadata field `human_owner` is `Hall` for the MVP. Hall remains the final approval authority for live marketing execution.

## Required Approval Metadata

```json
{
  "approval_required": true,
  "human_owner": "Hall",
  "approval_state": "pending_human",
  "review_agent": "hall-marketing-reviewer",
  "live_platform_access": false
}
```

## Approval States

| State | Meaning |
|---|---|
| `not_requested` | Work item exists but is not ready for human approval |
| `pending_review` | Specialist output is ready for reviewer inspection |
| `pending_human` | Reviewer/HQ output is ready for Hall |
| `approved` | Hall approved the specific next step |
| `rejected` | Hall rejected the specific next step |
| `blocked` | Missing evidence, missing access, or unsafe request |

## First PR Enforcement

The first implementation PR should enforce safety by construction:

- Hard-code `approval_required=true` for the mock endpoint.
- Hard-code `live_platform_access=false` for all work items and evidence.
- Do not add credentials or platform clients.
- Do not add background schedules.
- Do not write to external platforms.
- Return a response that explicitly says the run is mock-only.

## Future Approval Requirements

Before live integrations are added, define separate approval gates for:

| Gate | Required before |
|---|---|
| Read-only platform connection approval | Pulling live data from Google Ads, HubSpot, GA4, Search Console, Slack, or Monday |
| Recommendation approval | Treating generated recommendations as accepted planning actions |
| Write approval | Any production write to ad platforms, CRM, project management, communications, or content systems |
| Spend approval | Budget, bid, campaign, or audience changes |
| Publishing approval | Any customer-facing content or notification |

## Audit Language

All mock outputs should include language equivalent to:

```text
This is a mock-only MVP evidence packet. It does not contain live platform data and must not be used as authorization for production marketing changes.
```
