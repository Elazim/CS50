"""deliverable_generate pipeline: build the spec, render every format,
persist an immutable version.

Idempotent on retry: a version row already created by this run is reused,
never duplicated — and versions are never mutated after finalize.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFoundError
from app.modules.deliverables.models import Deliverable, DeliverableVersion
from app.modules.deliverables.render import MIME_BY_FORMAT, render_all
from app.modules.deliverables.specs import GENERATOR_VERSION, build_spec
from app.modules.projects.models import Project
from app.storage import put_object_bytes
from app.worker.runner import StepContext


def build_and_render(session: Session, ctx: StepContext) -> tuple[dict, int]:
    run = ctx.run
    deliverable_id = uuid.UUID(run.context["deliverable_id"])
    deliverable = session.get(Deliverable, deliverable_id)
    if deliverable is None:
        raise NotFoundError("Deliverable not found")
    project = session.get(Project, deliverable.project_id)
    if project is None:
        raise NotFoundError("Project not found")

    existing = session.execute(
        select(DeliverableVersion)
        .where(DeliverableVersion.deliverable_id == deliverable.id)
        .order_by(DeliverableVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None and existing.spec.get("_run_id") == str(run.id):
        return {"version": existing.version, "reused": True}, 0

    spec = build_spec(session, project, deliverable.type)
    spec["_run_id"] = str(run.id)
    version_number = (existing.version if existing else 0) + 1

    artifacts: dict[str, str] = {}
    rendered = render_all(deliverable.type, spec)
    for fmt, data in rendered.items():
        key = (
            f"org/{run.org_id}/projects/{project.id}/deliverables/"
            f"{deliverable.id}/v{version_number}/{deliverable.type.value}.{fmt}"
        )
        put_object_bytes(key, data, MIME_BY_FORMAT[fmt])
        artifacts[fmt] = key

    requested_by = run.context.get("requested_by")
    session.add(
        DeliverableVersion(
            org_id=run.org_id,
            deliverable_id=deliverable.id,
            version=version_number,
            spec=spec,
            artifacts=artifacts,
            generator_version=GENERATOR_VERSION,
            created_by=uuid.UUID(requested_by) if requested_by else None,
        )
    )
    session.flush()
    return {
        "version": version_number,
        "formats": sorted(artifacts),
        "citations": len(spec["citations"]),
    }, 0


def finalize(session: Session, ctx: StepContext) -> tuple[dict, int]:
    deliverable = session.get(
        Deliverable, uuid.UUID(ctx.run.context["deliverable_id"])
    )
    if deliverable is None:
        raise NotFoundError("Deliverable not found")
    latest = session.execute(
        select(DeliverableVersion.version)
        .where(DeliverableVersion.deliverable_id == deliverable.id)
        .order_by(DeliverableVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    deliverable.latest_version = latest or 0
    session.flush()
    return {"latest_version": deliverable.latest_version}, 0
