from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_loop import MARKETING_REPOSITORY, MARKETING_WORKFLOW_TYPE, REVIEW_AGENT
from app.marketing_sheets_evidence_adapter import (
    MarketingSheetsEvidenceValidationError,
    MarketingSheetsSourceReadError,
    attach_google_sheets_readonly_evidence,
)
from app.marketing_sheets_evidence_contract import AttachGoogleSheetsReadOnlyEvidenceRequest
from app.marketing_summary import build_marketing_workflow_summary


class FakeSheetsEvidenceAgentBusClient:
    def __init__(self, work_items: list[dict[str, object]] | None = None) -> None:
        self.work_items: list[dict[str, object]] = work_items or []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.created_evidence_packets: list[dict[str, object]] = []
        self.attached_evidence: list[tuple[str, dict[str, object]]] = []
        self.external_writes: list[str] = []

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        if repository is None:
            return self.work_items
        return [item for item in self.work_items if item.get("repository") == repository]

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = f"ev-{uuid4()}"
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets[evidence_id] = packet
        self.created_evidence_packets.append(packet)
        return packet

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        try:
            return self.evidence_packets[evidence_id]
        except KeyError as exc:
            raise AgentBusAPIError("GET", f"/evidence-packets/{evidence_id}", 404, "Evidence packet not found") from exc

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        self.attached_evidence.append((work_item_id, payload))
        item = self._item(work_item_id)
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            evidence_ids = metadata.setdefault("evidence_packet_ids", [])
            if isinstance(evidence_ids, list):
                evidence_ids.append(payload["evidence_id"])
        return item

    def add_mock_evidence(self, item: dict[str, object]) -> None:
        evidence_id = f"ev-{uuid4()}"
        packet = {
            "evidence_id": evidence_id,
            "work_item_id": item["work_item_id"],
            "repository": MARKETING_REPOSITORY,
            "implementation_agent": item["owner_agent"],
            "test_results": {
                "evidence_type": "ppc_snapshot",
                "mode": "mock_only",
                "confidence": "mock_only",
                "live_platform_access": False,
            },
        }
        self.evidence_packets[evidence_id] = packet
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("evidence_packet_ids", []).append(evidence_id)

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")


class StaticSheetsReader:
    def __init__(self, rows: list[dict[str, object]] | None = None, *, fail: bool = False) -> None:
        self.rows = rows if rows is not None else [
            {"source": "organic", "leads": 30, "contacts_created": 28, "deals_created": 4, "sessions": 800},
            {"source": "paid", "leads": 12, "contacts_created": 10, "deals_created": 2, "sessions": 400},
        ]
        self.fail = fail
        self.reads: list[str] = []
        self.writes: list[str] = []

    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, object]]:
        self.reads.append(payload.source_id)
        if self.fail:
            raise MarketingSheetsSourceReadError("Unable to read configured test source.")
        return self.rows


def marketing_work_item(
    *,
    agent_id: str = "hall-data-intelligence",
    workflow_id: str = "marketing-wf-sheets",
    live_platform_access: bool = False,
) -> dict[str, object]:
    return {
        "work_item_id": f"wi-{uuid4()}",
        "title": f"Marketing work item: {agent_id}",
        "repository": MARKETING_REPOSITORY,
        "status": "queued",
        "owner_agent": agent_id,
        "review_agent": REVIEW_AGENT,
        "created_at": "2026-06-26T12:00:00Z",
        "updated_at": "2026-06-26T12:00:00Z",
        "metadata": {
            "domain": "marketing",
            "workflow_id": workflow_id,
            "workflow_type": MARKETING_WORKFLOW_TYPE,
            "work_item_role": "specialist_evidence",
            "mock_mode": True,
            "mvp_mode": "mock_only",
            "live_platform_access": live_platform_access,
            "approval_required": True,
        },
    }


def request_payload(work_item_id: str, *, workflow_id: str = "marketing-wf-sheets", agent_id: str = "hall-data-intelligence") -> dict[str, object]:
    return {
        "workflow_id": workflow_id,
        "agent_id": agent_id,
        "work_item_id": work_item_id,
        "source_type": "google_sheet",
        "source_id": "SAFE_TEST_SOURCE_ID",
        "sheet_name": "Weekly Marketing Snapshot",
        "date_range_label": "last_7_days",
        "mapping": {
            "leads": "leads",
            "contacts_created": "contacts_created",
            "deals_created": "deals_created",
            "sessions": "sessions",
            "source": "source",
        },
    }


def client_with_fake_agent_bus(
    fake_client: FakeSheetsEvidenceAgentBusClient,
    *,
    enable_sheets: bool,
    reader: StaticSheetsReader | None = None,
) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_marketing_sheets_readonly_evidence=enable_sheets,
    )
    app.state.agent_bus_client = fake_client
    if reader is not None:
        app.state.marketing_sheets_source_reader = reader
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    for attr in {"agent_bus_client", "marketing_sheets_source_reader"}:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    get_settings.cache_clear()


def test_sheets_endpoint_requires_admin_auth() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_sheets=True, reader=StaticSheetsReader())

    response = client.post("/api/v1/marketing/evidence/google-sheets-readonly/attach", json=request_payload(str(item["work_item_id"])))

    assert response.status_code == 401


def test_sheets_endpoint_respects_feature_flag() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_sheets=False, reader=StaticSheetsReader())

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_SHEETS_READONLY_EVIDENCE" in response.json()["detail"]


def test_sheets_adapter_rejects_unsupported_agent() -> None:
    item = marketing_work_item(agent_id="hall-ppc-intelligence")
    fake = FakeSheetsEvidenceAgentBusClient([item])

    with pytest.raises(MarketingSheetsEvidenceValidationError, match="hall-data-intelligence"):
        asyncio.run(
            attach_google_sheets_readonly_evidence(
                agent_bus_client=fake,
                source_reader=StaticSheetsReader(),
                payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]), agent_id="hall-ppc-intelligence")),
            )
        )


def test_sheets_adapter_rejects_missing_source() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])

    with pytest.raises(MarketingSheetsSourceReadError, match="No rows returned"):
        asyncio.run(
            attach_google_sheets_readonly_evidence(
                agent_bus_client=fake,
                source_reader=StaticSheetsReader(rows=[]),
                payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]))),
            )
        )


def test_sheets_read_only_source_creates_analytics_snapshot() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])

    response = asyncio.run(
        attach_google_sheets_readonly_evidence(
            agent_bus_client=fake,
            source_reader=StaticSheetsReader(),
            payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert response.evidence_type == "analytics_snapshot"
    assert response.source_mode == "google_sheets_readonly"
    packet = fake.created_evidence_packets[0]
    results = packet["test_results"]
    assert isinstance(results, dict)
    assert results["evidence_type"] == "analytics_snapshot"


def test_sheets_evidence_includes_source_mode_and_no_write_fields() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])

    asyncio.run(
        attach_google_sheets_readonly_evidence(
            agent_bus_client=fake,
            source_reader=StaticSheetsReader(),
            payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    results = fake.created_evidence_packets[0]["test_results"]
    assert isinstance(results, dict)
    assert results["source_mode"] == "google_sheets_readonly"
    assert results["write_access"] is False
    assert results["live_platform_access"] is False
    assert results["not_for_real_marketing_decisions"] is True


def test_sheets_derived_metric_calculation_works() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])

    response = asyncio.run(
        attach_google_sheets_readonly_evidence(
            agent_bus_client=fake,
            source_reader=StaticSheetsReader(),
            payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert response.metrics["leads"] == 42
    assert response.metrics["contacts_created"] == 38
    assert response.metrics["deals_created"] == 6
    assert response.metrics["sessions"] == 1200
    assert response.metrics["deal_created_rate_from_leads"] == 0.1429


def test_sheets_source_read_errors_return_clear_endpoint_response() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_sheets=True, reader=StaticSheetsReader(fail=True))

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 502
    assert "Unable to read configured test source" in response.json()["detail"]


def test_sheets_endpoint_reports_connector_gap_when_reader_is_unconfigured() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])
    client = client_with_fake_agent_bus(fake, enable_sheets=True)

    response = client.post(
        "/api/v1/marketing/evidence/google-sheets-readonly/attach",
        headers={"Authorization": "Bearer admin-token"},
        json=request_payload(str(item["work_item_id"])),
    )

    assert response.status_code == 502
    assert "No Google Sheets or Drive CSV read-only source reader is configured" in response.json()["detail"]


def test_summary_includes_google_sheets_readonly_source_mode() -> None:
    workflow_id = "marketing-wf-sheets"
    data_item = marketing_work_item(workflow_id=workflow_id)
    ppc_item = marketing_work_item(agent_id="hall-ppc-intelligence", workflow_id=workflow_id)
    fake = FakeSheetsEvidenceAgentBusClient([data_item, ppc_item])
    fake.add_mock_evidence(ppc_item)
    asyncio.run(
        attach_google_sheets_readonly_evidence(
            agent_bus_client=fake,
            source_reader=StaticSheetsReader(),
            payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(data_item["work_item_id"]), workflow_id=workflow_id)),
        )
    )

    summary = asyncio.run(
        build_marketing_workflow_summary(
            workflow_id,
            agent_bus_client=fake,
            agent_bus_mission_control_url="/agent-bus",
            orchestrator_snapshot_url="/orchestrator",
        )
    )

    assert summary.evidence_source_modes["google_sheets_readonly"] == 1
    assert summary.evidence_source_modes["mock_generated"] == 1


def test_sheets_adapter_does_not_call_write_methods() -> None:
    item = marketing_work_item()
    fake = FakeSheetsEvidenceAgentBusClient([item])
    reader = StaticSheetsReader()

    asyncio.run(
        attach_google_sheets_readonly_evidence(
            agent_bus_client=fake,
            source_reader=reader,
            payload=AttachGoogleSheetsReadOnlyEvidenceRequest(**request_payload(str(item["work_item_id"]))),
        )
    )

    assert fake.external_writes == []
    assert reader.writes == []
