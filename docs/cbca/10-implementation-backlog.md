# Implementation Backlog

## Priority 0: Documentation And Planning

| Item | Repo | Status |
|---|---|---|
| Convert audit into repo-native CBCA docs | `riseos-agent-orchestrator` | Implemented |
| Define Marketing Agent Loop MVP PR | `riseos-agent-orchestrator` | Implemented in `12-mvp-marketing-loop-pr-plan.md` |
| Confirm Vultr service names and ports | Ops | Open |
| Confirm Agent Bus evidence packet endpoint availability | `jarvis-agent-bus-mcp` | Evidence route used by mock loop |

## Priority 1: Mock Marketing Loop MVP

| Item | Repo | Notes |
|---|---|---|
| Add marketing workflow request/response models | `riseos-agent-orchestrator` | Pydantic models, no live integrations |
| Add admin-protected mock-run endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/weekly-command-brief/mock-run` |
| Extend Agent Bus client methods | `riseos-agent-orchestrator` | Register agents, create work, attach evidence/review artifacts |
| Add marketing agent registry seed helper | `riseos-agent-orchestrator` | Idempotent registration of six MVP agents |
| Add mock evidence generator | `riseos-agent-orchestrator` | Deterministic packet content |
| Add canonical mock review and HQ synthesis artifacts | `riseos-agent-orchestrator` | `risk_review` and `synthesis_memo` artifacts |
| Add tests for endpoint and payloads | `riseos-agent-orchestrator` | Use mocked Agent Bus client |
| Add local curl validation docs | `riseos-agent-orchestrator` | Include endpoint and snapshot checks |

## Priority 1A: Marketing Worker Adapter Contract

| Item | Repo | Notes |
|---|---|---|
| Add marketing worker registry | `riseos-agent-orchestrator` | Routing/validation only, live integrations disabled |
| Add worker adapter contract models | `riseos-agent-orchestrator` | Run-once request/response and per-item result |
| Add callable mock worker adapter | `riseos-agent-orchestrator` | Poll, claim, mark in progress, attach evidence, complete |
| Add admin-protected run-once endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/workers/mock/run-once` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_WORKER_MOCK=true` required |
| Add deferred specialist completion option | `riseos-agent-orchestrator` | `auto_complete_specialists=false` lets worker attach evidence |
| Add worker adapter tests | `riseos-agent-orchestrator` | Registry, eligibility, safety flags, endpoint auth |

## Priority 1B: Marketing Governance Stage Runner

| Item | Repo | Notes |
|---|---|---|
| Add governance run contract models | `riseos-agent-orchestrator` | Run-once request/response and reviewer/HQ stage results |
| Add callable mock governance runner | `riseos-agent-orchestrator` | Validates specialist evidence, then creates review and synthesis artifacts |
| Add admin-protected governance endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/governance/mock/run-once` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_GOVERNANCE_MOCK=true` required |
| Update summary next actions | `riseos-agent-orchestrator` | Worker first, then reviewer/HQ, then Hall review |
| Add governance runner tests | `riseos-agent-orchestrator` | Auth, flag, evidence validation, artifact references, mock safeguards |

## Priority 1C: Mock Human Approval

| Item | Repo | Notes |
|---|---|---|
| Add approval request/response models | `riseos-agent-orchestrator` | Supports `approve_mock`, `reject_mock`, and `request_changes` |
| Add durable approval recorder | `riseos-agent-orchestrator` | Attaches `human_approval` evidence to the HQ synthesis work item |
| Add admin-protected approval endpoints | `riseos-agent-orchestrator` | `POST` and `GET /api/v1/marketing/workflows/{workflow_id}/approval` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_APPROVAL_MOCK=true` required for POST |
| Update summary approval state | `riseos-agent-orchestrator` | Shows approval decision and no-production-write status |
| Add approval tests | `riseos-agent-orchestrator` | Auth, flag, missing prerequisites, decisions, summary, safeguards |

## Priority 1D: Read-Only Fixture Evidence Adapter

| Item | Repo | Notes |
|---|---|---|
| Add fixture evidence request/response models | `riseos-agent-orchestrator` | Weekly marketing snapshot fixture only |
| Add Hall Data Intelligence fixture adapter | `riseos-agent-orchestrator` | Supports only `hall-data-intelligence -> analytics_snapshot` |
| Add admin-protected fixture attach endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/evidence/read-only-fixture/attach` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_READONLY_EVIDENCE=true` required |
| Update summary source-mode counts | `riseos-agent-orchestrator` | Shows `mock_generated` and `read_only_fixture` counts |
| Add fixture evidence tests | `riseos-agent-orchestrator` | Auth, flag, mapping, metrics, safety fields, summary counts |

## Priority 1E: Google Sheets / Drive Read-Only Evidence Adapter

| Item | Repo | Notes |
|---|---|---|
| Add Sheets/Drive evidence request/response models | `riseos-agent-orchestrator` | Supports `google_sheet` and `drive_csv` source descriptors |
| Add swappable read-only tabular source interface | `riseos-agent-orchestrator` | Local test double first; real connector can be wired later |
| Add Hall Data Intelligence Sheets adapter | `riseos-agent-orchestrator` | Supports only `hall-data-intelligence -> analytics_snapshot` |
| Add admin-protected Sheets attach endpoint | `riseos-agent-orchestrator` | `POST /api/v1/marketing/evidence/google-sheets-readonly/attach` |
| Add safe execution flag | `riseos-agent-orchestrator` | `ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE=true` required |
| Preserve no-write evidence safeguards | `riseos-agent-orchestrator` | `live_platform_access=false`, `write_access=false`, planning-only evidence |
| Keep summary source-mode counts generic | `riseos-agent-orchestrator` | Counts `google_sheets_readonly` and `drive_csv_readonly` when present |
| Add Sheets adapter tests | `riseos-agent-orchestrator` | Auth, flag, mapping, source errors, metrics, safeguards, summary counts |

## Priority 1F: Approved Google Sheets Read-Only Source Reader

| Item | Repo | Notes |
|---|---|---|
| Add source ID allowlist config | `riseos-agent-orchestrator` | `MARKETING_READONLY_ALLOWED_SOURCE_IDS` comma-separated list |
| Add service-account credential path config | `riseos-agent-orchestrator` | Uses deployment-provided `GOOGLE_APPLICATION_CREDENTIALS` |
| Wire approved Google Sheets reader | `riseos-agent-orchestrator` | Reads only explicit allowlisted Sheet IDs and explicit tab names |
| Use read-only Sheets scope | `riseos-agent-orchestrator` | `https://www.googleapis.com/auth/spreadsheets.readonly` only |
| Fail closed on unsafe reads | `riseos-agent-orchestrator` | Missing credentials, allowlist, sheet, columns, date rows, or Google read failure |
| Preserve evidence contract | `riseos-agent-orchestrator` | Emits `source_mode=google_sheets_readonly`, no-write safeguards, and planning-only confidence |
| Add approved-reader tests | `riseos-agent-orchestrator` | Allowlist, credentials, schema, filtering, metrics, no write methods |

## Priority 1G: Read-Only Evidence Audit Logging

| Item | Repo | Notes |
|---|---|---|
| Add marketing evidence audit contract | `riseos-agent-orchestrator` | Records sanitized attach-attempt events |
| Add durable JSONL audit repository | `riseos-agent-orchestrator` | Uses `ORCHESTRATOR_DB_PATH` sibling JSONL when configured |
| Audit Google Sheets attach attempts | `riseos-agent-orchestrator` | Success and failure events for the read-only evidence endpoint |
| Add admin-protected audit read endpoint | `riseos-agent-orchestrator` | `GET /api/v1/marketing/evidence/audit` with filters |
| Redact source and secret material | `riseos-agent-orchestrator` | Stores source hash and last six only; no credentials or auth headers |
| Add audit tests | `riseos-agent-orchestrator` | Success, failures, redaction, auth, filters, no-write fields |
| Defer summary audit counts | `riseos-agent-orchestrator` | Use audit endpoint first; add summary counts later if needed |

## Priority 2: Agent Bus Evidence API Hardening

| Item | Repo | Notes |
|---|---|---|
| Confirm routes for evidence packet creation and attachment | `jarvis-agent-bus-mcp` | The lifecycle model exists; route availability should be verified |
| Add tests for evidence packet visibility in Mission Control | `jarvis-agent-bus-mcp` | If not already covered |
| Add metadata filters for marketing domain if needed | `jarvis-agent-bus-mcp` | Avoid until MVP proves need |
| Add idempotency support for repeated mock runs if needed | Both | Could use `workflow_run_id` or request id |

## Priority 3: Read-Only Platform Discovery

Do not start this until Hall explicitly approves live read-only integration work.

| Platform | First safe scope |
|---|---|
| Google Sheets / Drive CSV | Read-only weekly snapshot import through an explicitly configured source reader |
| Google Ads | Read-only account/campaign summary |
| GA4 | Read-only weekly traffic/conversion summary |
| Search Console | Read-only query/page summary |
| HubSpot | Read-only lifecycle/source summary |
| Slack | Notification-only summaries, no workflow action |
| Monday | Read-only board/task summary or explicit approved writeback |

## Priority 4: Human Approval UX

| Item | Notes |
|---|---|
| Approval packet schema | Implemented for mock approvals; real-data approval remains separate |
| Approval state transitions | Mock approval states added before live writes |
| Mission Control marketing filter | Show marketing runs clearly |
| Reviewer queue view | Show `hall-marketing-reviewer` queue and evidence |

## Priority 5: Live Execution Gates

Only after read-only integrations are stable and Hall approves write behavior.

| Gate | Required proof |
|---|---|
| Live read gate | Credentials stored safely, no writes possible, audit logs available |
| Recommendation gate | Evidence packets use real source labels and confidence levels |
| Write gate | Explicit human approval, dry-run diff, rollback instructions |
| Spend gate | Budget limits, approval record, emergency stop |

## Backlog Guardrails

- Keep changes small and PR-scoped.
- Preserve public APIs until downstream usage is checked.
- Keep Agent Bus canonical for durable state.
- Keep Orchestrator responsible for workflow decisions.
- Avoid new dependencies unless they remove real complexity.
- Treat all marketing recommendations as planning-only until approved.
