import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.audit import audit
from app.deps import OrgCtx
from app.errors import AppError, NotFoundError
from app.modules.accounts.models import Role
from app.modules.documents.models import Document
from app.modules.knowledge import bpmn as bpmn_export
from app.modules.knowledge import service
from app.modules.knowledge.models import (
    Confidence,
    Entity,
    EntityRelation,
    Evidence,
    ReviewItem,
    ReviewItemStatus,
    ReviewState,
)
from app.modules.pipelines.service import enqueue_run
from app.modules.projects.models import Project

router = APIRouter(tags=["knowledge"])


# ---------- extraction ----------


class ExtractOut(BaseModel):
    pipeline_run_id: uuid.UUID


@router.post(
    "/orgs/{org_id}/projects/{project_id}/knowledge/extract",
    response_model=ExtractOut,
    status_code=202,
)
def start_extraction(project_id: uuid.UUID, ctx: OrgCtx) -> ExtractOut:
    ctx.require_role(Role.analyst)
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")
    run = enqueue_run(
        ctx.db, org_id=ctx.org_id, project_id=project_id,
        kind="knowledge_extract", context={},
    )
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="knowledge.extract_started", resource_type="project",
          resource_id=project_id, meta={"run_id": str(run.id)})
    return ExtractOut(pipeline_run_id=run.id)


# ---------- entities ----------


class EvidenceOut(BaseModel):
    element_id: uuid.UUID
    document_id: uuid.UUID
    filename: str | None = None
    quote: str | None


class EntityOut(BaseModel):
    id: uuid.UUID
    type: str
    name: str
    attrs: dict
    confidence: Confidence
    review_state: ReviewState
    novel: bool
    version: int
    created_at: datetime
    evidence: list[EvidenceOut] = []

    model_config = {"from_attributes": True}


class KnowledgeSummaryOut(BaseModel):
    entities_by_type: dict[str, int]
    by_review_state: dict[str, int]
    open_review_items: int


@router.get(
    "/orgs/{org_id}/projects/{project_id}/knowledge/summary",
    response_model=KnowledgeSummaryOut,
)
def knowledge_summary(project_id: uuid.UUID, ctx: OrgCtx) -> KnowledgeSummaryOut:
    by_type: dict[str, int] = defaultdict(int)
    by_state: dict[str, int] = defaultdict(int)
    for entity_type, state, count in ctx.db.execute(
        select(Entity.type, Entity.review_state, func.count())
        .where(Entity.project_id == project_id)
        .group_by(Entity.type, Entity.review_state)
    ):
        if state != ReviewState.rejected:
            by_type[entity_type] += count
        by_state[state.value] += count
    open_items = ctx.db.execute(
        select(func.count()).select_from(ReviewItem).where(
            ReviewItem.project_id == project_id,
            ReviewItem.status == ReviewItemStatus.open,
        )
    ).scalar_one()
    return KnowledgeSummaryOut(
        entities_by_type=dict(by_type),
        by_review_state=dict(by_state),
        open_review_items=open_items,
    )


@router.get(
    "/orgs/{org_id}/projects/{project_id}/entities",
    response_model=list[EntityOut],
)
def list_entities(
    project_id: uuid.UUID,
    ctx: OrgCtx,
    type: str | None = None,
    review_state: ReviewState | None = None,
    include_rejected: bool = False,
    limit: int = 200,
) -> list[EntityOut]:
    query = select(Entity).where(Entity.project_id == project_id)
    if type:
        query = query.where(Entity.type == type)
    if review_state:
        query = query.where(Entity.review_state == review_state)
    elif not include_rejected:
        query = query.where(Entity.review_state != ReviewState.rejected)
    entities = (
        ctx.db.execute(query.order_by(Entity.type, Entity.name).limit(min(limit, 500)))
        .scalars()
        .all()
    )
    return _with_evidence(ctx, entities)


def _with_evidence(ctx: OrgCtx, entities) -> list[EntityOut]:
    ids = [e.id for e in entities]
    evidence_map: dict[uuid.UUID, list[EvidenceOut]] = defaultdict(list)
    if ids:
        rows = ctx.db.execute(
            select(Evidence, Document.filename)
            .join(Document, Document.id == Evidence.document_id)
            .where(Evidence.claimable_type == "entity", Evidence.claimable_id.in_(ids))
        ).all()
        for evidence, filename in rows:
            if len(evidence_map[evidence.claimable_id]) < 5:
                evidence_map[evidence.claimable_id].append(
                    EvidenceOut(
                        element_id=evidence.element_id,
                        document_id=evidence.document_id,
                        filename=filename,
                        quote=evidence.quote,
                    )
                )
    out = []
    for entity in entities:
        item = EntityOut.model_validate(entity)
        item.evidence = evidence_map.get(entity.id, [])
        out.append(item)
    return out


# ---------- review ----------


class EntityReviewIn(BaseModel):
    action: str  # confirm | reject | edit
    edits: dict | None = None


@router.post("/orgs/{org_id}/entities/{entity_id}/review", response_model=EntityOut)
def review_entity(entity_id: uuid.UUID, body: EntityReviewIn, ctx: OrgCtx) -> EntityOut:
    ctx.require_role(Role.analyst)
    entity = ctx.db.get(Entity, entity_id)
    if entity is None:
        raise NotFoundError("Entity not found")
    service.review_entity(
        ctx.db, entity=entity, action=body.action, user_id=ctx.user.id, edits=body.edits
    )
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action=f"entity.{body.action}", resource_type="entity", resource_id=entity.id)
    return _with_evidence(ctx, [entity])[0]


class ReviewItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    subject_type: str
    subject_id: uuid.UUID
    question: str
    payload: dict
    status: str
    created_at: datetime
    subject: EntityOut | None = None

    model_config = {"from_attributes": True}


@router.get(
    "/orgs/{org_id}/projects/{project_id}/review-items",
    response_model=list[ReviewItemOut],
)
def list_review_items(
    project_id: uuid.UUID, ctx: OrgCtx, status: ReviewItemStatus = ReviewItemStatus.open,
    limit: int = 100,
) -> list[ReviewItemOut]:
    items = (
        ctx.db.execute(
            select(ReviewItem)
            .where(ReviewItem.project_id == project_id, ReviewItem.status == status)
            .order_by(ReviewItem.created_at)
            .limit(min(limit, 300))
        )
        .scalars()
        .all()
    )
    entity_ids = [i.subject_id for i in items if i.subject_type == "entity"]
    entities = {}
    if entity_ids:
        loaded = ctx.db.execute(select(Entity).where(Entity.id.in_(entity_ids))).scalars()
        entity_outs = _with_evidence(ctx, list(loaded))
        entities = {e.id: e for e in entity_outs}
    out = []
    for item in items:
        view = ReviewItemOut.model_validate(item)
        view.kind = item.kind.value
        view.status = item.status.value
        view.subject = entities.get(item.subject_id)
        out.append(view)
    return out


class ResolveIn(BaseModel):
    action: str  # for merge_proposal: merge | keep_separate; otherwise: dismiss


@router.post("/orgs/{org_id}/review-items/{item_id}/resolve", response_model=ReviewItemOut)
def resolve_review_item(item_id: uuid.UUID, body: ResolveIn, ctx: OrgCtx) -> ReviewItemOut:
    ctx.require_role(Role.analyst)
    item = ctx.db.get(ReviewItem, item_id)
    if item is None:
        raise NotFoundError("Review item not found")
    if item.status != ReviewItemStatus.open:
        raise AppError("Review item is already resolved")

    if item.kind.value == "merge_proposal" and body.action == "merge":
        keep = ctx.db.get(Entity, item.subject_id)
        merge = ctx.db.get(Entity, uuid.UUID(item.payload["other_id"]))
        if keep is None or merge is None:
            raise NotFoundError("Entity in proposal no longer exists")
        service.merge_entities(ctx.db, keep=keep, merge=merge, user_id=ctx.user.id)
        item.status = ReviewItemStatus.resolved
    elif body.action in ("keep_separate", "dismiss"):
        item.status = ReviewItemStatus.dismissed
    else:
        raise AppError(f"Unknown resolution action: {body.action}")
    item.resolved_by = ctx.user.id
    item.resolution = {"action": body.action}
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action=f"review_item.{body.action}", resource_type="review_item",
          resource_id=item.id)
    view = ReviewItemOut.model_validate(item)
    view.kind = item.kind.value
    view.status = item.status.value
    return view


# ---------- process graph + BPMN ----------


class GraphNodeOut(BaseModel):
    id: uuid.UUID
    name: str
    step_type: str
    order: int
    lane: str
    review_state: ReviewState
    pain_points: list[dict] = []
    evidence: list[EvidenceOut] = []


class GraphEdgeOut(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID


class ProcessGraphOut(BaseModel):
    process: EntityOut
    lanes: list[str]
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


def _load_graph(ctx: OrgCtx, process_id: uuid.UUID) -> ProcessGraphOut:
    process = ctx.db.get(Entity, process_id)
    if process is None or process.type != "process":
        raise NotFoundError("Process not found")

    step_ids = [
        row[0]
        for row in ctx.db.execute(
            select(EntityRelation.from_id).where(
                EntityRelation.to_id == process_id, EntityRelation.rel_type == "part_of"
            )
        )
    ]
    steps = []
    if step_ids:
        steps = list(
            ctx.db.execute(
                select(Entity).where(
                    Entity.id.in_(step_ids), Entity.review_state != ReviewState.rejected
                )
            ).scalars()
        )
    relations = list(
        ctx.db.execute(
            select(EntityRelation).where(
                EntityRelation.from_id.in_(step_ids + [process_id])
                | EntityRelation.to_id.in_(step_ids + [process_id])
            )
        ).scalars()
    ) if step_ids else []

    performer_by_step: dict[uuid.UUID, str] = {}
    pain_by_target: dict[uuid.UUID, list[dict]] = defaultdict(list)
    actor_ids = {r.from_id for r in relations if r.rel_type == "performs"}
    pain_ids = {r.from_id for r in relations if r.rel_type == "affects"}
    names = {
        e.id: e
        for e in ctx.db.execute(
            select(Entity).where(Entity.id.in_(actor_ids | pain_ids))
        ).scalars()
    } if (actor_ids or pain_ids) else {}
    for relation in relations:
        if relation.rel_type == "performs" and relation.from_id in names:
            performer_by_step[relation.to_id] = names[relation.from_id].name
        if relation.rel_type == "affects" and relation.from_id in names:
            pain = names[relation.from_id]
            if pain.review_state != ReviewState.rejected:
                pain_by_target[relation.to_id].append(
                    {"id": str(pain.id), "name": pain.name,
                     "taxonomy": pain.attrs.get("taxonomy")}
                )

    step_outs = _with_evidence(ctx, steps)
    evidence_by_id = {s.id: s.evidence for s in step_outs}
    nodes = sorted(
        (
            GraphNodeOut(
                id=step.id,
                name=step.name,
                step_type=step.attrs.get("step_type", "system"),
                order=step.attrs.get("order", 0),
                lane=performer_by_step.get(step.id, "Unassigned"),
                review_state=step.review_state,
                pain_points=pain_by_target.get(step.id, [])
                + pain_by_target.get(process_id, []),
                evidence=evidence_by_id.get(step.id, []),
            )
            for step in steps
        ),
        key=lambda n: n.order,
    )
    edges = [
        GraphEdgeOut(from_id=r.from_id, to_id=r.to_id)
        for r in relations
        if r.rel_type == "precedes"
    ]
    return ProcessGraphOut(
        process=_with_evidence(ctx, [process])[0],
        lanes=sorted({n.lane for n in nodes}),
        nodes=nodes,
        edges=edges,
    )


@router.get("/orgs/{org_id}/processes/{process_id}/graph", response_model=ProcessGraphOut)
def process_graph(process_id: uuid.UUID, ctx: OrgCtx) -> ProcessGraphOut:
    return _load_graph(ctx, process_id)


@router.get("/orgs/{org_id}/processes/{process_id}/bpmn")
def process_bpmn(process_id: uuid.UUID, ctx: OrgCtx) -> Response:
    graph = _load_graph(ctx, process_id)
    xml = bpmn_export.build_bpmn(
        graph.process.name,
        [
            bpmn_export.GraphNode(
                id=str(n.id), name=n.name, step_type=n.step_type,
                order=n.order, lane=n.lane, pain_points=n.pain_points,
            )
            for n in graph.nodes
        ],
        [bpmn_export.GraphEdge(str(e.from_id), str(e.to_id)) for e in graph.edges],
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition":
                f'attachment; filename="{graph.process.name[:40]}.bpmn"'
        },
    )
