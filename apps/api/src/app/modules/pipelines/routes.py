import asyncio
import json
import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.db import get_session_factory, set_org_context
from app.deps import OrgCtx
from app.errors import NotFoundError
from app.modules.pipelines.models import PipelineRun, RunStatus, StepStatus

router = APIRouter(prefix="/orgs/{org_id}/pipeline-runs", tags=["pipelines"])


class StepOut(BaseModel):
    name: str
    status: StepStatus
    attempt: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    status: RunStatus
    context: dict
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepOut]

    model_config = {"from_attributes": True}


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, ctx: OrgCtx) -> RunOut:
    run = ctx.db.get(PipelineRun, run_id)
    if run is None:
        raise NotFoundError("Pipeline run not found")
    return RunOut.model_validate(run)


@router.get("/{run_id}/events")
async def run_events(run_id: uuid.UUID, ctx: OrgCtx) -> EventSourceResponse:
    """SSE stream of run snapshots until the run reaches a terminal state.

    M0 implementation polls the database once per second — honest, simple,
    and replaceable by LISTEN/NOTIFY without changing the wire contract.
    """
    org_id = ctx.org_id  # capture before the request-scoped session closes

    def snapshot() -> RunOut | None:
        session = get_session_factory()()
        try:
            set_org_context(session, org_id)
            run = session.get(PipelineRun, run_id)
            return RunOut.model_validate(run) if run else None
        finally:
            session.close()

    initial = await asyncio.to_thread(snapshot)
    if initial is None:
        raise NotFoundError("Pipeline run not found")

    async def stream():
        current = initial
        while True:
            yield {"event": "run", "data": json.dumps(current.model_dump(mode="json"))}
            if current.status in (RunStatus.succeeded, RunStatus.failed):
                return
            await asyncio.sleep(1.0)
            refreshed = await asyncio.to_thread(snapshot)
            if refreshed is None:
                return
            current = refreshed

    return EventSourceResponse(stream())
