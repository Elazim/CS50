"""Checkpointed pipeline runner (docs/02 §3, docs/04).

A pipeline is an ordered list of named steps. Each step records an
`input_hash`; on retry, a step whose prior attempt succeeded with the same
hash is skipped. This makes runs resumable and idempotent without relying
on broker delivery semantics — the property that makes Celery safe here.
"""

import hashlib
import json
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.modules.pipelines.models import PipelineRun, PipelineStep, RunStatus, StepStatus

log = get_logger("pipeline")


@dataclass
class StepContext:
    """Mutable bag passed through a run's steps; step outputs accumulate here."""

    run: PipelineRun
    outputs: dict[str, dict] = field(default_factory=dict)


# A step returns (output_ref, cost_tokens).
StepFn = Callable[[Session, StepContext], tuple[dict, int]]


@dataclass(frozen=True)
class StepDef:
    name: str
    fn: StepFn
    version: str = "1"


def step_input_hash(step: StepDef, ctx: StepContext) -> str:
    payload = {"context": ctx.run.context, "version": step.version}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def execute_run(session: Session, run: PipelineRun) -> None:
    from app.worker.pipelines import PIPELINES  # late import to avoid cycles

    steps = PIPELINES.get(run.kind)
    if steps is None:
        _fail_run(session, run, f"Unknown pipeline kind: {run.kind}")
        return

    run.status = RunStatus.running
    run.started_at = run.started_at or datetime.now(UTC)
    session.flush()

    ctx = StepContext(run=run)
    for step in steps:
        input_hash = step_input_hash(step, ctx)
        existing = session.execute(
            select(PipelineStep).where(
                PipelineStep.run_id == run.id, PipelineStep.name == step.name
            )
        ).scalar_one_or_none()

        if (
            existing is not None
            and existing.status == StepStatus.succeeded
            and existing.input_hash == input_hash
        ):
            ctx.outputs[step.name] = existing.output_ref or {}
            log.info("step.skipped", run_id=str(run.id), step=step.name)
            continue

        if existing is None:
            existing = PipelineStep(
                run_id=run.id,
                org_id=run.org_id,
                name=step.name,
                status=StepStatus.running,
                input_hash=input_hash,
            )
            session.add(existing)
        else:
            existing.attempt += 1
            existing.status = StepStatus.running
            existing.input_hash = input_hash
            existing.error = None
        existing.started_at = datetime.now(UTC)
        session.flush()

        try:
            output_ref, cost_tokens = step.fn(session, ctx)
        except Exception as exc:
            existing.status = StepStatus.failed
            existing.error = f"{exc}\n{traceback.format_exc(limit=5)}"
            existing.finished_at = datetime.now(UTC)
            _fail_run(session, run, f"Step '{step.name}' failed: {exc}")
            log.error("step.failed", run_id=str(run.id), step=step.name, error=str(exc))
            return

        existing.status = StepStatus.succeeded
        existing.output_ref = output_ref
        existing.cost_tokens = cost_tokens
        existing.finished_at = datetime.now(UTC)
        ctx.outputs[step.name] = output_ref
        session.flush()
        log.info("step.succeeded", run_id=str(run.id), step=step.name)

    run.status = RunStatus.succeeded
    run.finished_at = datetime.now(UTC)
    session.flush()
    log.info("run.succeeded", run_id=str(run.id), kind=run.kind)


def _fail_run(session: Session, run: PipelineRun, error: str) -> None:
    run.status = RunStatus.failed
    run.error = error
    run.finished_at = datetime.now(UTC)
    session.flush()
