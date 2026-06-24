# Evidence Packet Standards

## Purpose

Evidence packets are the audit trail for what each specialist did, what was checked, what assumptions were made, and what remains unverified. For the first Marketing Agent Loop PR, evidence packets must be mock-only but still structurally useful.

## Existing Agent Bus Evidence Model

Agent Bus has a canonical evidence packet model in `src/agent_bus_mcp/review_lifecycle.py`:

```json
{
  "work_item_id": "uuid",
  "repository": "hall-source/riseos-agent-orchestrator",
  "issue_number": null,
  "pr_number": null,
  "implementation_agent": "hall-data-intelligence",
  "branch": "agent-integration",
  "commit_shas": [],
  "changed_files": [],
  "test_commands": [],
  "test_results": {},
  "verification_summary": "Mock data intelligence evidence generated for MVP validation.",
  "assumptions": [],
  "unverified_items": []
}
```

The first PR should reuse this structure if the installed Agent Bus route supports creating these packets. If a direct route is missing or inconvenient, the fallback is to attach evidence packet IDs or mock evidence summaries in work-item metadata until the API is extended.

## Mock Evidence Packet Format

Recommended specialist evidence metadata:

```json
{
  "evidence_schema": "marketing.mock_evidence.v1",
  "workflow_run_id": "uuid",
  "domain": "marketing",
  "brand": "rise",
  "business_unit": "RISE Commercial District",
  "agent_id": "hall-ppc-intelligence",
  "evidence_type": "ppc_evidence",
  "period_start": "2026-06-17",
  "period_end": "2026-06-24",
  "summary": "Mock PPC evidence generated for MVP validation.",
  "findings": [
    "Paid-search spend posture requires review before scaling.",
    "Campaign-level recommendations are simulated and must not be applied live."
  ],
  "recommended_actions": [
    "Review query intent categories before budget movement.",
    "Prepare approval checklist for future live read-only data integration."
  ],
  "confidence": "mock",
  "source_systems": ["mock"],
  "live_platform_access": false,
  "approval_required": true
}
```

## Required Evidence Fields

| Field | Required | Notes |
|---|---:|---|
| `evidence_schema` | Yes | Start with `marketing.mock_evidence.v1` |
| `workflow_run_id` | Yes | Same ID across all workflow items |
| `agent_id` | Yes | Must match owner agent |
| `evidence_type` | Yes | Must match work-item `output_kind` |
| `summary` | Yes | Human-readable summary |
| `findings` | Yes | Bullet-ready evidence findings |
| `recommended_actions` | Yes | Recommendations requiring review |
| `confidence` | Yes | Use `mock` for MVP |
| `source_systems` | Yes | Use `["mock"]` for MVP |
| `live_platform_access` | Yes | Must be `false` |
| `approval_required` | Yes | Must be `true` |

## Specialist Evidence Expectations

| Agent | Evidence type | Minimum findings |
|---|---|---|
| `hall-data-intelligence` | `data_evidence` | KPI summary, data-quality caveat, measurement next step |
| `hall-ppc-intelligence` | `ppc_evidence` | Paid-media posture, budget caveat, query/campaign review next step |
| `hall-seo-intelligence` | `seo_evidence` | Organic opportunity, content gap, technical or intent caveat |
| `hall-creative-strategist` | `creative_evidence` | Offer angle, creative test, audience/messaging caveat |
| `hall-marketing-reviewer` | `review_summary` | Risk summary, approval requirements, unresolved questions |
| `clone-banks-hq` | `executive_synthesis` | Prioritized command brief, decisions needed, human approval handoff |

## Review Evidence Standard

The reviewer work item should not simply mark the workflow approved. It should produce a review packet or evidence summary that states:

- What specialist packets were reviewed.
- Which recommendations are safe as planning-only next steps.
- Which items require Hall approval.
- Which future platform connections are still blocked.
- Which data is simulated.

## Human-Readable Final Brief Standard

The Clone Banks HQ synthesis item should include a concise command brief in metadata or evidence:

```markdown
# Weekly Marketing Command Brief

## Situation

## Channel Intelligence

## Recommended Priorities

## Approval Needed

## Unverified / Mock-Only Items
```

## Safety Rules

- Never present mock findings as real platform data.
- Every mock packet must say `source_systems: ["mock"]`.
- Every mock packet must say `live_platform_access: false`.
- Every recommendation must remain planning-only until Hall approves live execution.
