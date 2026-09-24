"""Unit tests for CSV prospect import."""

from __future__ import annotations

from uuid import UUID

import pytest

from prospectiq.application.prospect_import import ProspectImportService
from prospectiq.domain.common import TenantId, TenantScope, WorkspaceId
from prospectiq.domain.jobs import JobType
from prospectiq.domain.prospect_import import ImportedProspectStatus
from prospectiq.infrastructure.jobs import InMemoryJobQueue
from tests.fakes import InMemoryImportBatchRepository, InMemoryImportedProspectRepository

TENANT = TenantId(UUID("00000000-0000-0000-0000-000000000001"))
WORKSPACE = WorkspaceId(UUID("00000000-0000-0000-0000-000000000002"))


def _scope() -> TenantScope:
    return TenantScope(tenant_id=TENANT, workspace_id=WORKSPACE)


SAMPLE_CSV = b"""First Name,Last Name,Email,Email Status,Title,Company Name,Website,\
Company Domain,# Employees
Jane,Doe,jane@acme.test,verified,CTO,Acme Inc,https://acme.test,acme.test,120
John,Smith,john@acme.test,verified,Engineer,Acme Inc,https://acme.test,acme.test,120
,,,,,,,
Bob,Lee,bob@other.test,,CEO,Other Co,https://other.test,other.test,50
"""


def _service() -> tuple[
    ProspectImportService, InMemoryJobQueue, InMemoryImportedProspectRepository
]:
    queue = InMemoryJobQueue()
    batches = InMemoryImportBatchRepository()
    prospects = InMemoryImportedProspectRepository()
    service = ProspectImportService(batches=batches, prospects=prospects, jobs=queue)
    return service, queue, prospects


def _find_import_job(queue: InMemoryJobQueue) -> object:
    for job in queue.jobs.values():
        if job.job_type is JobType.IMPORT_PROSPECTS:
            return job
    raise AssertionError("IMPORT_PROSPECTS job not found")


@pytest.mark.asyncio
async def test_preview_csv() -> None:
    service, _, _ = _service()
    preview = service.preview_csv(SAMPLE_CSV)
    assert preview.estimated_row_count == 4
    assert "first_name" in preview.column_mapping.values()
    assert preview.sample_rows[0]["normalized"]["email"] == "jane@acme.test"


@pytest.mark.asyncio
async def test_import_creates_prospects_and_detects_duplicates() -> None:
    service, queue, prospects_repo = _service()
    submission = await service.submit_import(
        _scope(), filename="test.csv", content=SAMPLE_CSV, provider="apollo"
    )
    job = _find_import_job(queue)
    result = await service.execute_job(job)
    assert result.imported_rows == 3
    assert result.duplicate_rows == 0
    assert result.skipped_rows == 1
    stored = await prospects_repo.list_for_tenant(_scope(), batch_id=submission.batch_id, limit=100)
    imported = [p for p in stored if p.status is ImportedProspectStatus.IMPORTED]
    assert len(imported) == 3
    assert imported[0].normalized_data["company_domain"] == "acme.test"


@pytest.mark.asyncio
async def test_import_detects_duplicate_email_in_batch() -> None:
    csv_dup = b"""First Name,Last Name,Email,Company Name,Company Domain
A,One,a@test.com,Co,a.test
B,Two,a@test.com,Co,a.test
"""
    service, queue, prospects_repo = _service()
    submission = await service.submit_import(_scope(), filename="dup.csv", content=csv_dup)
    job = _find_import_job(queue)
    result = await service.execute_job(job)
    assert result.imported_rows == 1
    assert result.duplicate_rows == 1
    stored = await prospects_repo.list_for_tenant(_scope(), batch_id=submission.batch_id, limit=10)
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_import_job_enqueued_with_batch_id() -> None:
    service, queue, _ = _service()
    submission = await service.submit_import(_scope(), filename="t.csv", content=SAMPLE_CSV)
    job = _find_import_job(queue)
    assert job.payload["import_batch_id"] == str(submission.batch_id)
