from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from kaos_core import KaosContext

from kaos_source.connectors import (
    ArchiveConnector,
    BrowserConnector,
    FilesystemConnector,
    HttpConnector,
    MemoryConnector,
    SourceConnector,
)
from kaos_source.errors import SourceError, SourceNotFoundError, SourceValidationError
from kaos_source.models import (
    SourceDescriptor,
    SourceJob,
    SourceJobResult,
    SourceJobStatus,
    SourceKind,
    SourceLocator,
    SourceMaterialization,
    SourceOperation,
    SourcePage,
    SourcePreview,
)
from kaos_source.options import (
    SourceDiscoverOptions,
    SourceMaterializeOptions,
    SourcePreviewOptions,
)

SourceOperationOptions = (
    SourceDiscoverOptions | SourcePreviewOptions | SourceMaterializeOptions | None
)
SourceOperationResult = SourceDescriptor | SourcePage | SourcePreview | SourceMaterialization


class SourceService:
    def __init__(
        self,
        *,
        connectors: list[SourceConnector] | None = None,
        max_concurrent_operations: int = 4,
    ) -> None:
        self._connectors: dict[SourceKind, SourceConnector] = {}
        self._jobs: dict[str, SourceJob] = {}
        self._job_tasks: dict[str, asyncio.Task[None]] = {}
        self._operation_semaphore = asyncio.Semaphore(max_concurrent_operations)

        default_connectors = connectors
        if default_connectors is None:
            default_connectors = [
                FilesystemConnector(),
                ArchiveConnector(),
                MemoryConnector(),
                HttpConnector(),
                BrowserConnector(),
            ]
        for connector in default_connectors:
            self.register_connector(connector)

    def register_connector(self, connector: SourceConnector) -> None:
        self._connectors[connector.kind] = connector

    def connector_for(self, locator: SourceLocator) -> SourceConnector:
        try:
            return self._connectors[locator.source_kind]
        except KeyError as exc:
            raise SourceValidationError(
                "No source connector is registered for locator kind",
                source_kind=locator.source_kind,
                locator=locator.uri,
            ) from exc

    def memory(self) -> MemoryConnector:
        connector = self._connectors.get(SourceKind.MEMORY)
        if not isinstance(connector, MemoryConnector):
            raise SourceValidationError("Memory connector is not registered")
        return connector

    def register_memory_bytes(
        self,
        name: str,
        payload: bytes,
        *,
        mime_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SourceLocator:
        return self.memory().put_bytes(name, payload, mime_type=mime_type, metadata=metadata)

    async def describe(self, locator: SourceLocator, context: KaosContext) -> SourceDescriptor:
        return await self.connector_for(locator).describe(locator, context)

    async def discover(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceDiscoverOptions | None = None,
    ) -> SourcePage:
        return await self.connector_for(locator).discover(locator, context, options)

    async def preview(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourcePreviewOptions | None = None,
    ) -> SourcePreview:
        return await self.connector_for(locator).preview(locator, context, options)

    async def materialize(
        self,
        locator: SourceLocator,
        context: KaosContext,
        options: SourceMaterializeOptions | None = None,
    ) -> SourceMaterialization:
        return await self.connector_for(locator).materialize(locator, context, options)

    async def start_job(
        self,
        locator: SourceLocator,
        context: KaosContext,
        *,
        operation: SourceOperation,
        options: SourceOperationOptions = None,
        metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> SourceJob:
        connector = self.connector_for(locator)
        submitted_at = self._timestamp()
        job = SourceJob(
            job_id=str(uuid4()),
            operation=operation,
            status=SourceJobStatus.QUEUED,
            submitted_at=submitted_at,
            locator=locator,
            metadata=metadata or {},
            message=message,
        )
        self._jobs[job.job_id] = job
        self._job_tasks[job.job_id] = asyncio.create_task(
            self._run_job(job.job_id, connector, locator, context, operation, options)
        )
        return job

    def get_job(self, job_id: str) -> SourceJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise SourceNotFoundError("Unknown source job", job_id=job_id) from exc

    async def cancel_job(self, job_id: str) -> SourceJob:
        job = self.get_job(job_id)
        if job.status in {
            SourceJobStatus.CANCELLED,
            SourceJobStatus.SUCCEEDED,
            SourceJobStatus.FAILED,
        }:
            return job

        task = self._job_tasks.get(job_id)
        if task is None:
            return job
        task.cancel()
        job.status = SourceJobStatus.CANCELLED
        job.finished_at = self._timestamp()
        job.message = job.message or "Cancelled"
        with contextlib.suppress(asyncio.CancelledError):
            await task
        return job

    async def wait_for_job(
        self,
        job_id: str,
        *,
        timeout: float = 5.0,
        poll_interval: float = 0.01,
    ) -> SourceJob:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            job = self.get_job(job_id)
            if job.status in {
                SourceJobStatus.SUCCEEDED,
                SourceJobStatus.FAILED,
                SourceJobStatus.CANCELLED,
            }:
                return job
            if asyncio.get_running_loop().time() >= deadline:
                return job
            await asyncio.sleep(poll_interval)

    async def _run_job(
        self,
        job_id: str,
        connector: SourceConnector,
        locator: SourceLocator,
        context: KaosContext,
        operation: SourceOperation,
        options: SourceOperationOptions,
    ) -> None:
        job = self._jobs[job_id]
        async with self._operation_semaphore:
            if job.status is SourceJobStatus.CANCELLED:
                return
            job.status = SourceJobStatus.IN_PROGRESS
            job.started_at = self._timestamp()
            job.message = job.message or f"Running {operation.value}"
            try:
                result = await self._dispatch_operation(
                    connector, locator, context, operation, options
                )
            except asyncio.CancelledError:
                job.status = SourceJobStatus.CANCELLED
                job.finished_at = self._timestamp()
                job.message = "Cancelled"
                raise
            except SourceError as exc:
                job.status = SourceJobStatus.FAILED
                job.finished_at = self._timestamp()
                job.error = exc.to_info()
                job.message = exc.message
                return
            except Exception as exc:
                error = SourceError(str(exc))
                job.status = SourceJobStatus.FAILED
                job.finished_at = self._timestamp()
                job.error = error.to_info()
                job.message = str(exc)
                return

            if job.status is SourceJobStatus.CANCELLED:
                return
            job.result = self._job_result(result)
            job.status = SourceJobStatus.SUCCEEDED
            job.finished_at = self._timestamp()
            job.progress_current = 1
            job.progress_total = 1
            job.message = "Completed"

    async def _dispatch_operation(
        self,
        connector: SourceConnector,
        locator: SourceLocator,
        context: KaosContext,
        operation: SourceOperation,
        options: SourceOperationOptions,
    ) -> SourceOperationResult:
        if operation is SourceOperation.DESCRIBE:
            return await connector.describe(locator, context)
        if operation is SourceOperation.DISCOVER:
            return await connector.discover(locator, context, self._as_discover_options(options))
        if operation is SourceOperation.PREVIEW:
            return await connector.preview(locator, context, self._as_preview_options(options))
        if operation is SourceOperation.MATERIALIZE:
            return await connector.materialize(
                locator, context, self._as_materialize_options(options)
            )
        raise SourceValidationError("Unsupported source operation", operation=operation)

    @staticmethod
    def _job_result(result: SourceOperationResult) -> SourceJobResult:
        payload = SourceJobResult()
        if isinstance(result, SourceDescriptor):
            payload.descriptor = result
        elif isinstance(result, SourcePage):
            payload.page = result
        elif isinstance(result, SourcePreview):
            payload.preview = result
        else:
            payload.materialization = result
        return payload

    @staticmethod
    def _as_discover_options(options: SourceOperationOptions) -> SourceDiscoverOptions | None:
        if options is None or isinstance(options, SourceDiscoverOptions):
            return options
        raise SourceValidationError(
            "Invalid options for discover operation", options_type=type(options).__name__
        )

    @staticmethod
    def _as_preview_options(options: SourceOperationOptions) -> SourcePreviewOptions | None:
        if options is None or isinstance(options, SourcePreviewOptions):
            return options
        raise SourceValidationError(
            "Invalid options for preview operation", options_type=type(options).__name__
        )

    @staticmethod
    def _as_materialize_options(options: SourceOperationOptions) -> SourceMaterializeOptions | None:
        if options is None or isinstance(options, SourceMaterializeOptions):
            return options
        raise SourceValidationError(
            "Invalid options for materialize operation",
            options_type=type(options).__name__,
        )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(tz=UTC).isoformat()
