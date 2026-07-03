import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.deps import OrgCtx
from app.errors import NotFoundError
from app.modules.projects.models import Project
from app.modules.retrieval.service import search_chunks

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    top_k: int = Field(default=8, ge=1, le=25)


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_class: str | None
    text: str
    score: float
    section_path: list
    pages: list
    element_ids: list[uuid.UUID]


@router.post(
    "/orgs/{org_id}/projects/{project_id}/search",
    response_model=list[SearchHit],
)
def search_project(project_id: uuid.UUID, body: SearchRequest, ctx: OrgCtx) -> list[SearchHit]:
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")
    results = search_chunks(
        ctx.db, project_id=project_id, query=body.query, top_k=body.top_k
    )
    return [SearchHit(**vars(r)) for r in results]
