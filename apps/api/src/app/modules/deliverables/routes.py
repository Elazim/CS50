import uuid
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.audit import audit
from app.deps import OrgCtx
from app.errors import AppError, NotFoundError
from app.modules.accounts.models import Role
from app.modules.deliverables.models import Deliverable, DeliverableType, DeliverableVersion
from app.modules.deliverables.render import FORMATS_BY_TYPE, MIME_BY_FORMAT
from app.modules.pipelines.service import enqueue_run
from app.modules.projects.models import Project
from app.storage import get_object_bytes

router = APIRouter(tags=["deliverables"])


class DeliverableCreate(BaseModel):
    type: DeliverableType


class DeliverableOut(BaseModel):
    id: uuid.UUID
    type: DeliverableType
    title: str
    latest_version: int
    formats: list[str] = []
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateDeliverableOut(BaseModel):
    deliverable: DeliverableOut
    pipeline_run_id: uuid.UUID


@router.post(
    "/orgs/{org_id}/projects/{project_id}/deliverables",
    response_model=GenerateDeliverableOut,
    status_code=202,
)
def generate_deliverable(
    project_id: uuid.UUID, body: DeliverableCreate, ctx: OrgCtx
) -> GenerateDeliverableOut:
    """Get-or-create the deliverable for this (project, type) and produce a
    new immutable version of it."""
    ctx.require_role(Role.analyst)
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")

    deliverable = ctx.db.execute(
        select(Deliverable).where(
            Deliverable.project_id == project_id, Deliverable.type == body.type
        )
    ).scalar_one_or_none()
    if deliverable is None:
        deliverable = Deliverable(
            org_id=ctx.org_id,
            project_id=project_id,
            type=body.type,
            title=body.type.value.replace("_", " ").title(),
        )
        ctx.db.add(deliverable)
        ctx.db.flush()

    run = enqueue_run(
        ctx.db, org_id=ctx.org_id, project_id=project_id,
        kind="deliverable_generate",
        context={
            "deliverable_id": str(deliverable.id),
            "requested_by": str(ctx.user.id),
        },
    )
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="deliverable.generate_started", resource_type="deliverable",
          resource_id=deliverable.id, meta={"type": body.type.value})
    view = DeliverableOut.model_validate(deliverable)
    view.formats = FORMATS_BY_TYPE[deliverable.type]
    return GenerateDeliverableOut(deliverable=view, pipeline_run_id=run.id)


@router.get(
    "/orgs/{org_id}/projects/{project_id}/deliverables",
    response_model=list[DeliverableOut],
)
def list_deliverables(project_id: uuid.UUID, ctx: OrgCtx) -> list[DeliverableOut]:
    deliverables = (
        ctx.db.execute(
            select(Deliverable)
            .where(Deliverable.project_id == project_id)
            .order_by(Deliverable.created_at)
        )
        .scalars()
        .all()
    )
    out = []
    for deliverable in deliverables:
        view = DeliverableOut.model_validate(deliverable)
        view.formats = FORMATS_BY_TYPE[deliverable.type]
        out.append(view)
    return out


class VersionOut(BaseModel):
    id: uuid.UUID
    version: int
    generator_version: str
    formats: list[str]
    review_coverage: str | None
    citation_count: int
    created_at: datetime


@router.get(
    "/orgs/{org_id}/deliverables/{deliverable_id}/versions",
    response_model=list[VersionOut],
)
def list_versions(deliverable_id: uuid.UUID, ctx: OrgCtx) -> list[VersionOut]:
    if ctx.db.get(Deliverable, deliverable_id) is None:
        raise NotFoundError("Deliverable not found")
    versions = (
        ctx.db.execute(
            select(DeliverableVersion)
            .where(DeliverableVersion.deliverable_id == deliverable_id)
            .order_by(DeliverableVersion.version.desc())
        )
        .scalars()
        .all()
    )
    return [
        VersionOut(
            id=v.id,
            version=v.version,
            generator_version=v.generator_version,
            formats=sorted(v.artifacts),
            review_coverage=v.spec.get("review_coverage"),
            citation_count=len(v.spec.get("citations", [])),
            created_at=v.created_at,
        )
        for v in versions
    ]


class SpecOut(BaseModel):
    version: int
    spec: dict


@router.get("/orgs/{org_id}/deliverable-versions/{version_id}/spec", response_model=SpecOut)
def get_spec(version_id: uuid.UUID, ctx: OrgCtx) -> SpecOut:
    version = ctx.db.get(DeliverableVersion, version_id)
    if version is None:
        raise NotFoundError("Version not found")
    spec = {k: v for k, v in version.spec.items() if not k.startswith("_")}
    return SpecOut(version=version.version, spec=spec)


@router.get("/orgs/{org_id}/deliverable-versions/{version_id}/download")
def download(version_id: uuid.UUID, format: str, ctx: OrgCtx) -> Response:
    version = ctx.db.get(DeliverableVersion, version_id)
    if version is None:
        raise NotFoundError("Version not found")
    key = version.artifacts.get(format)
    if key is None:
        raise AppError(f"Format '{format}' not available for this version")
    deliverable = ctx.db.get(Deliverable, version.deliverable_id)
    if deliverable is None:
        raise NotFoundError("Deliverable not found")
    data = get_object_bytes(key)
    filename = f"{deliverable.type.value}-v{version.version}.{format}"
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="deliverable.downloaded", resource_type="deliverable_version",
          resource_id=version.id, meta={"format": format})
    return Response(
        content=data,
        media_type=MIME_BY_FORMAT.get(format, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
