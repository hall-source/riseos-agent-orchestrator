# CBCA Executive Summary

## Purpose

This CBCA documentation set converts the audit and marketing-agent roadmap into repo-native markdown so it can be used as durable project knowledge for ChatGPT Projects, implementation planning, and future PR review.

The immediate goal is not to connect live marketing systems. The immediate goal is to document the current Agent Bus and Orchestrator architecture, define the marketing-agent contract, and prepare the first small MVP PR that proves the marketing command brief loop with mock work items and evidence packets.

## Current System Shape

| Repo | Role | Current evidence |
|---|---|---|
| `riseos-agent-orchestrator` | External orchestration layer for workflows, routing, GitHub webhook handling, queue visibility, and Agent Bus dispatch | FastAPI app in `app/main.py`, config in `app/config.py`, Agent Bus client in `app/clients/agent_bus.py`, snapshot route at `GET /api/v1/orchestrator/snapshot` |
| `jarvis-agent-bus-mcp` | Canonical communication, handoff, work-item, agent-registry, evidence, and mission-control ledger | FastAPI app in `src/agent_bus_mcp/api.py`, models in `src/agent_bus_mcp/models.py`, review lifecycle in `src/agent_bus_mcp/review_lifecycle.py`, snapshot route at `GET /api/v1/mission-control/snapshot` |

## Recommended Direction

The Marketing Agent Loop should be implemented as an orchestrator-driven workflow that writes canonical work state into Agent Bus. Agent Bus should remain the source of truth for agents, work items, evidence packets, review packets, and Mission Control visibility.

The first implementation PR should prove this loop only with simulated workers and mock evidence:

```text
manual marketing command brief request
-> orchestrator creates mock/simulated specialist work items
-> Agent Bus stores work items
-> fake worker/evidence function attaches evidence packets
-> reviewer work item is created
-> Clone Banks HQ synthesis item is created
-> final state is visible through mission-control/snapshot
```

## MVP Agent Set

| Agent ID | Role |
|---|---|
| `clone-banks-hq` | Marketing command synthesis and executive brief owner |
| `hall-data-intelligence` | Data and measurement specialist |
| `hall-ppc-intelligence` | Paid search and paid media specialist |
| `hall-seo-intelligence` | SEO and organic demand specialist |
| `hall-creative-strategist` | Creative, messaging, and offer specialist |
| `hall-marketing-reviewer` | Human-approval-oriented reviewer |

## Non-Goals For First PR

- No Google Ads integration.
- No HubSpot integration.
- No GA4 integration.
- No Google Search Console integration.
- No Slack or Monday automation.
- No public API renames.
- No production behavior changes by default.
- No autonomous approvals or publishing.

## Implementation Principle

Use existing primitives first:

- Agent Bus `POST /agents` for registry seed.
- Agent Bus `POST /work-items` for specialist, reviewer, and synthesis items.
- Existing work-item metadata for marketing workflow fields.
- Existing evidence/review packet lifecycle where available.
- Existing mission-control and orchestrator snapshots for visibility.

Only add a new orchestrator endpoint if it gives a clearer manual trigger than overloading GitHub webhook or debug routes.
