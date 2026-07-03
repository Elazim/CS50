import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.audit import audit
from app.deps import OrgCtx
from app.errors import NotFoundError
from app.modules.accounts.models import Role
from app.modules.projects.models import Project, ProjectStatus

router = APIRouter(prefix="/orgs/{org_id}/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry_pack: str = "insurance-claims"


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    industry_pack: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[ProjectOut])
def list_projects(ctx: OrgCtx) -> list[ProjectOut]:
    rows = (
        ctx.db.execute(
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ProjectOut.model_validate(p) for p in rows]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, ctx: OrgCtx) -> ProjectOut:
    ctx.require_role(Role.analyst)
    project = Project(org_id=ctx.org_id, name=body.name, industry_pack=body.industry_pack)
    ctx.db.add(project)
    ctx.db.flush()
    audit(
        ctx.db,
        org_id=ctx.org_id,
        actor_id=ctx.user.id,
        action="project.created",
        resource_type="project",
        resource_id=project.id,
        meta={"name": project.name},
    )
    return ProjectOut.model_validate(project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, ctx: OrgCtx) -> ProjectOut:
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")
    return ProjectOut.model_validate(project)
