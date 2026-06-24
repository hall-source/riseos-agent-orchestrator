# Open Questions

## Questions For Hall

| Question | Why it matters |
|---|---|
| Is `RISE Commercial District` the exact business-unit label to use everywhere? | Prevents inconsistent metadata and future filtering issues |
| Should `Hall` always be the human owner for marketing approvals? | Defines final approval boundary |
| Should Marcus be recorded as `requested_by` for manual runs? | Helps audit manual triggers |
| What weekly reporting period should default when dates are omitted? | Endpoint can either require dates or compute them |
| Should Clone Banks HQ produce a markdown brief inside metadata, an evidence packet, or a future document artifact? | Determines where synthesis output lives |
| Is `hall-marketing-reviewer` allowed to mark items `approved`, or only `pending_human`? | Clarifies agent review vs human approval |
| Which Mission Control view should be considered the acceptance target? | Agent Bus snapshot, orchestrator snapshot, or both |

## Questions For Marcus

| Question | Why it matters |
|---|---|
| What are the exact Vultr service names for Orchestrator and Agent Bus? | Needed for verification commands and future deployment notes |
| What ports are currently used on Vultr? | Prevents conflicting local validation instructions |
| Are Orchestrator and Agent Bus running on the same host? | Determines `AGENT_BUS_BASE_URL` value |
| Is `AGENT_BUS_DB` persisted on disk today? | Determines whether Mission Control state survives restarts |
| Is `ORCHESTRATOR_DB_PATH` configured today? | Determines whether orchestrator state survives restarts |
| Are admin tokens required for debug reads in the current environment? | Changes curl validation headers |
| Is there a reverse proxy path for Mission Control? | Determines public validation URL |

## Questions For Implementation

| Question | Suggested default |
|---|---|
| Should the first endpoint be marketing-specific or reuse `/api/v1/agent-tasks`? | Add marketing-specific mock endpoint |
| Should agent seeding update existing records or only ignore duplicates? | Ignore duplicates first; add update only if needed |
| Should evidence packets use the Agent Bus review lifecycle API or work-item metadata? | Use lifecycle API if route is already exposed; otherwise metadata fallback |
| Should the endpoint synchronously create all work items and evidence? | Yes for MVP validation simplicity |
| Should repeated mock runs be idempotent? | Not required if each run gets a new workflow ID |
| Should tests use live Agent Bus? | Unit tests should mock Agent Bus; optional integration tests can run against local Agent Bus |

## Current Unknowns

- The original DOCX audit file was not present in the active workspace during this conversion.
- The docs were reconstructed from the requested audit section list plus inspected repository files and READMEs.
- The exact Vultr systemd unit files were not verified from committed repo files.
- Agent Bus evidence packet models are confirmed, but route support for creating and attaching canonical evidence packets should be verified before implementation.

## Decision Log To Fill Later

| Date | Decision | Owner |
|---|---|---|
| TBD | First endpoint shape approved or changed | Hall |
| TBD | Evidence storage route confirmed | Marcus / CBCA |
| TBD | Mission Control acceptance target confirmed | Hall / Marcus |
| TBD | Live read-only platform scope approved | Hall |
