from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.clients.agent_bus import AgentBusAPIError
from app.config import Settings, get_settings
from app.main import app
from app.marketing_evidence_audit import InMemoryMarketingEvidenceAuditRepository
from app.marketing_loop import MARKETING_REPOSITORY
from app.marketing_sheets_evidence_contract import AttachGoogleSheetsReadOnlyEvidenceRequest


class FakeWrapperAgentBusClient:
    def __init__(self, *, omit_data_item: bool = False) -> None:
        self.omit_data_item = omit_data_item
        self.work_items: list[dict[str, object]] = []
        self.evidence_packets: dict[str, dict[str, object]] = {}
        self.created_work_items: list[dict[str, object]] = []
        self.created_evidence_packets: list[dict[str, object]] = []
        self.external_writes: list[str] = []
        self.approvals: list[dict[str, object]] = []

    async def register_agent(self, payload: dict[str, object]) -> dict[str, object]:
        return {"agent_id": payload.get("agent_id")}

    async def heartbeat_agent(self, payload: dict[str, object]) -> dict[str, object]:
        return {"agent_id": payload.get("agent_id")}

    async def create_work_item(self, payload: dict[str, object]) -> dict[str, object]:
        work_item_id = f"wi-{uuid4()}"
        item = {
            **payload,
            "work_item_id": work_item_id,
            "status": "queued",
            "created_at": "2026-06-30T12:00:00Z",
            "updated_at": "2026-06-30T12:00:00Z",
        }
        self.created_work_items.append(item)
        if not (self.omit_data_item and payload.get("owner_agent") == "hall-data-intelligence"):
            self.work_items.append(item)
        return item

    async def list_work_items(self, *, repository: str | None = None) -> list[dict[str, object]]:
        return [item for item in self.work_items if repository is None or item.get("repository") == repository]

    async def create_evidence_packet(self, payload: dict[str, object]) -> dict[str, object]:
        evidence_id = f"ev-{uuid4()}"
        packet = {**payload, "evidence_id": evidence_id}
        self.evidence_packets[evidence_id] = packet
        self.created_evidence_packets.append(packet)
        return packet

    async def attach_evidence_to_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        item = self._item(work_item_id)
        metadata = item.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.setdefault("evidence_packet_ids", []).append(payload["evidence_id"])
        return item

    async def get_evidence_packet(self, evidence_id: str) -> dict[str, object]:
        try:
            return self.evidence_packets[evidence_id]
        except KeyError as exc:
            raise AgentBusAPIError("GET", f"/evidence-packets/{evidence_id}", 404, "Evidence packet not found") from exc

    async def claim_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        item = self._item(work_item_id)
        item["status"] = "claimed"
        return item

    async def transition_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        item = self._item(work_item_id)
        item["status"] = payload.get("status", item.get("status"))
        self._merge_metadata(item, payload.get("metadata"))
        return item

    async def complete_work_item(self, work_item_id: str, payload: dict[str, object]) -> dict[str, object]:
        item = self._item(work_item_id)
        item["status"] = "completed"
        self._merge_metadata(item, payload.get("metadata"))
        return item

    def _item(self, work_item_id: str) -> dict[str, object]:
        for item in self.work_items:
            if item.get("work_item_id") == work_item_id:
                return item
        raise AgentBusAPIError("GET", f"/work-items/{work_item_id}", 404, "Work item not found")

    @staticmethod
    def _merge_metadata(item: dict[str, object], metadata: object) -> None:
        if not isinstance(metadata, dict):
            return
        existing = item.setdefault("metadata", {})
        if isinstance(existing, dict):
            existing.update(metadata)


class StaticWrapperSheetsReader:
    def __init__(self) -> None:
        self.writes: list[str] = []

    async def read_rows(self, payload: AttachGoogleSheetsReadOnlyEvidenceRequest) -> list[dict[str, object]]:
        return [
            {"source": "paid_search", "leads": 18, "contacts_created": 16, "deals_created": 3, "sessions": 450},
            {"source": "organic_search", "leads": 14, "contacts_created": 12, "deals_created": 2, "sessions": 500},
            {"source": "direct", "leads": 10, "contacts_created": 10, "deals_created": 1, "sessions": 250},
        ]


VALID_SOURCE_ID = "1iJSBcqdOAlfFCFTOD_bpNoP0iDr3KNZfNnXgKO-Ewkw"


def wrapper_payload(*, source_id: str = VALID_SOURCE_ID, run_mock_workers: bool = True, run_mock_governance: bool = True) -> dict[str, object]:
    return {
        "business_unit": "RISE Commercial District",
        "requested_by": "Hall",
        "date_range_label": "last_7_days",
        "source_type": "google_sheet",
        "source_id": source_id,
        "sheet_name": "Weekly Marketing Snapshot",
        "run_mock_workers": run_mock_workers,
        "run_mock_governance": run_mock_governance,
    }


def client_with_wrapper(
    fake_client: FakeWrapperAgentBusClient,
    audit_repo: InMemoryMarketingEvidenceAuditRepository,
    *,
    reader: StaticWrapperSheetsReader | None = None,
    enable_wrapper: bool = True,
    enable_sheets: bool = True,
    enable_workers: bool = True,
    enable_governance: bool = True,
    allowed_source_ids: tuple[str, ...] = (VALID_SOURCE_ID,),
) -> TestClient:
    get_settings.cache_clear()
    app.dependency_overrides[get_settings] = lambda: Settings(
        github_webhook_secret="test-secret",
        orchestrator_admin_token="admin-token",
        agent_bus_base_url="http://127.0.0.1:8050",
        enable_weekly_marketing_snapshot_readonly=enable_wrapper,
        enable_marketing_sheets_readonly_evidence=enable_sheets,
        enable_marketing_worker_mock=enable_workers,
        enable_marketing_governance_mock=enable_governance,
        enable_marketing_approval_mock=True,
        marketing_readonly_allowed_source_ids=allowed_source_ids,
        google_application_credentials="/secure/test-service-account.json",
    )
    app.state.agent_bus_client = fake_client
    app.state.marketing_evidence_audit_repository = audit_repo
    if reader is not None:
        app.state.marketing_sheets_source_reader = reader
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()
    for attr in {"agent_bus_client", "marketing_sheets_source_reader", "marketing_evidence_audit_repository"}:
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    get_settings.cache_clear()


def test_wrapper_feature_flag_disabled_returns_403_without_side_effects() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(fake, audit_repo, reader=StaticWrapperSheetsReader(), enable_wrapper=False)

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(),
    )

    assert response.status_code == 403
    assert fake.created_work_items == []
    assert fake.created_evidence_packets == []
    assert audit_repo.events == []


def test_wrapper_happy_path_runs_without_auto_approval() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    reader = StaticWrapperSheetsReader()
    client = client_with_wrapper(fake, audit_repo, reader=reader)

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_id"].startswith("marketing-wf-")
    assert len(body["created_work_items"]) == 6
    assert body["data_work_item_id"]
    assert body["analytics_evidence_packet_id"]
    assert body["worker_run_id"]
    assert body["governance_run_id"]
    assert body["review_artifact_id"]
    assert body["synthesis_artifact_id"]
    assert body["audit_events_url"] == f"/api/v1/marketing/evidence/audit?workflow_id={body['workflow_id']}"
    assert body["summary_url"] == f"/api/v1/marketing/workflows/{body['workflow_id']}/summary"
    assert body["human_approval_performed"] is False
    assert body["approval_required"] is True
    assert body["live_platform_access"] is False
    assert body["write_access"] is False
    assert body["not_for_real_marketing_decisions"] is True
    assert fake.approvals == []
    assert fake.external_writes == []
    assert reader.writes == []
    assert audit_repo.events[-1].status == "success"

    summary_response = client.get(
        body["summary_url"],
        headers={"Authorization": "Bearer admin-token"},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["readiness"]["human_approval_ready"] is True
    assert summary["readiness"]["human_approval_complete"] is False
    assert summary["human_approval"]["state"] == "not_approved"


def test_wrapper_non_allowlisted_source_fails_safely_and_audits_failure() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(
        fake,
        audit_repo,
        reader=None,
        allowed_source_ids=("DIFFERENT_SOURCE",),
    )

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(source_id="NOT_ALLOWLISTED_SOURCE"),
    )

    assert response.status_code == 409
    assert audit_repo.events
    assert audit_repo.events[-1].status == "failed"
    assert audit_repo.events[-1].allowlist_passed is False
    assert fake.external_writes == []


def test_wrapper_missing_data_work_item_fails_cleanly() -> None:
    fake = FakeWrapperAgentBusClient(omit_data_item=True)
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(fake, audit_repo, reader=StaticWrapperSheetsReader())

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(),
    )

    assert response.status_code == 502
    assert "Hall Data Intelligence work item" in response.json()["detail"]


def test_wrapper_respects_worker_feature_flag() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(fake, audit_repo, reader=StaticWrapperSheetsReader(), enable_workers=False)

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(run_mock_workers=True),
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_WORKER_MOCK" in response.json()["detail"]
    assert fake.created_work_items == []


def test_wrapper_respects_governance_feature_flag() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(fake, audit_repo, reader=StaticWrapperSheetsReader(), enable_governance=False)

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(run_mock_governance=True),
    )

    assert response.status_code == 403
    assert "ENABLE_MARKETING_GOVERNANCE_MOCK" in response.json()["detail"]
    assert fake.created_work_items == []


def test_wrapper_can_skip_workers_and_governance() -> None:
    fake = FakeWrapperAgentBusClient()
    audit_repo = InMemoryMarketingEvidenceAuditRepository()
    client = client_with_wrapper(fake, audit_repo, reader=StaticWrapperSheetsReader())

    response = client.post(
        "/api/v1/marketing/workflows/weekly-snapshot/read-only/run",
        headers={"Authorization": "Bearer admin-token"},
        json=wrapper_payload(run_mock_workers=False, run_mock_governance=False),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["worker_run_id"] is None
    assert body["governance_run_id"] is None
    assert body["review_artifact_id"] is None
    assert body["synthesis_artifact_id"] is None
    assert body["human_approval_performed"] is False
