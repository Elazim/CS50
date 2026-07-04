import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.audit import audit
from app.deps import OrgCtx
from app.errors import AppError, NotFoundError
from app.modules.accounts.models import Role
from app.modules.documents.models import Document
from app.modules.knowledge.models import Entity, Evidence, ReviewState
from app.modules.knowledge.routes import EvidenceOut
from app.modules.opportunities import roi as roi_calc
from app.modules.opportunities import rubric
from app.modules.opportunities.models import (
    Opportunity,
    OpportunityTaxonomy,
    RoadmapHorizon,
    RoadmapItem,
    RoiModel,
)
from app.modules.pipelines.service import enqueue_run
from app.modules.projects.models import Project

router = APIRouter(tags=["opportunities"])


class GenerateOut(BaseModel):
    pipeline_run_id: uuid.UUID


@router.post(
    "/orgs/{org_id}/projects/{project_id}/opportunities/generate",
    response_model=GenerateOut,
    status_code=202,
)
def start_generation(project_id: uuid.UUID, ctx: OrgCtx) -> GenerateOut:
    ctx.require_role(Role.analyst)
    project = ctx.db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise NotFoundError("Project not found")
    run = enqueue_run(
        ctx.db, org_id=ctx.org_id, project_id=project_id,
        kind="opportunity_generate", context={},
    )
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="opportunities.generate_started", resource_type="project",
          resource_id=project_id, meta={"run_id": str(run.id)})
    return GenerateOut(pipeline_run_id=run.id)


class RoiOut(BaseModel):
    version: int
    assumptions: list[dict]
    computed: dict


class OpportunityOut(BaseModel):
    id: uuid.UUID
    process_id: uuid.UUID | None
    process_name: str | None = None
    taxonomy_type: OpportunityTaxonomy
    title: str
    description: str
    impact_score: int
    complexity_score: int
    risk_score: int
    rationale: str
    rubric_version: str
    review_state: ReviewState
    attrs: dict
    created_at: datetime
    evidence: list[EvidenceOut] = []
    roi: RoiOut | None = None

    model_config = {"from_attributes": True}


def _hydrate(ctx: OrgCtx, opportunities: list[Opportunity]) -> list[OpportunityOut]:
    ids = [o.id for o in opportunities]
    evidence_map: dict[uuid.UUID, list[EvidenceOut]] = defaultdict(list)
    roi_map: dict[uuid.UUID, RoiOut] = {}
    process_names: dict[uuid.UUID, str] = {}
    if ids:
        for evidence, filename in ctx.db.execute(
            select(Evidence, Document.filename)
            .join(Document, Document.id == Evidence.document_id)
            .where(
                Evidence.claimable_type == "opportunity",
                Evidence.claimable_id.in_(ids),
            )
        ).all():
            if len(evidence_map[evidence.claimable_id]) < 5:
                evidence_map[evidence.claimable_id].append(
                    EvidenceOut(
                        element_id=evidence.element_id,
                        document_id=evidence.document_id,
                        filename=filename,
                        quote=evidence.quote,
                    )
                )
        for roi_model in ctx.db.execute(
            select(RoiModel).where(RoiModel.opportunity_id.in_(ids))
        ).scalars():
            roi_map[roi_model.opportunity_id] = RoiOut(
                version=roi_model.version,
                assumptions=roi_model.assumptions,
                computed=roi_model.computed,
            )
        process_ids = {o.process_id for o in opportunities if o.process_id}
        if process_ids:
            for entity in ctx.db.execute(
                select(Entity).where(Entity.id.in_(process_ids))
            ).scalars():
                process_names[entity.id] = entity.name

    out = []
    for opportunity in opportunities:
        view = OpportunityOut.model_validate(opportunity)
        view.evidence = evidence_map.get(opportunity.id, [])
        view.roi = roi_map.get(opportunity.id)
        if opportunity.process_id:
            view.process_name = process_names.get(opportunity.process_id)
        out.append(view)
    return out


@router.get(
    "/orgs/{org_id}/projects/{project_id}/opportunities",
    response_model=list[OpportunityOut],
)
def list_opportunities(
    project_id: uuid.UUID, ctx: OrgCtx, include_rejected: bool = False
) -> list[OpportunityOut]:
    query = select(Opportunity).where(Opportunity.project_id == project_id)
    if not include_rejected:
        query = query.where(Opportunity.review_state != ReviewState.rejected)
    opportunities = list(
        ctx.db.execute(
            query.order_by(
                Opportunity.impact_score.desc(), Opportunity.complexity_score
            )
        ).scalars()
    )
    return _hydrate(ctx, opportunities)


class OpportunityReviewIn(BaseModel):
    action: str  # confirm | reject
    edits: dict | None = None  # {title?, description?}


@router.post(
    "/orgs/{org_id}/opportunities/{opportunity_id}/review",
    response_model=OpportunityOut,
)
def review_opportunity(
    opportunity_id: uuid.UUID, body: OpportunityReviewIn, ctx: OrgCtx
) -> OpportunityOut:
    ctx.require_role(Role.analyst)
    opportunity = ctx.db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise NotFoundError("Opportunity not found")
    if body.action == "confirm":
        opportunity.review_state = ReviewState.confirmed
    elif body.action == "reject":
        opportunity.review_state = ReviewState.rejected
    elif body.action == "edit":
        if body.edits:
            if "title" in body.edits:
                opportunity.title = str(body.edits["title"])[:300]
            if "description" in body.edits:
                opportunity.description = str(body.edits["description"])
        opportunity.review_state = ReviewState.edited
    else:
        raise AppError(f"Unknown review action: {body.action}")
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action=f"opportunity.{body.action}", resource_type="opportunity",
          resource_id=opportunity.id)
    return _hydrate(ctx, [opportunity])[0]


class RoiPatchIn(BaseModel):
    assumptions: list[dict] = Field(
        description="[{key, value}] — edited values; source becomes 'analyst'"
    )


@router.patch("/orgs/{org_id}/opportunities/{opportunity_id}/roi", response_model=RoiOut)
def patch_roi(opportunity_id: uuid.UUID, body: RoiPatchIn, ctx: OrgCtx) -> RoiOut:
    """Analyst edits assumptions; the arithmetic is recomputed in code —
    figures can never drift from the sheet (docs/01 §2.5)."""
    ctx.require_role(Role.analyst)
    roi_model = ctx.db.execute(
        select(RoiModel).where(RoiModel.opportunity_id == opportunity_id)
    ).scalar_one_or_none()
    if roi_model is None:
        raise NotFoundError("ROI model not found")
    edits = {str(a["key"]): a["value"] for a in body.assumptions if "key" in a}
    updated = []
    for assumption in roi_model.assumptions:
        if assumption["key"] in edits:
            try:
                value = float(edits[assumption["key"]])
            except (TypeError, ValueError) as exc:
                raise AppError(
                    f"Assumption '{assumption['key']}' must be numeric"
                ) from exc
            assumption = {**assumption, "value": value, "source": "analyst"}
        updated.append(assumption)
    roi_model.assumptions = updated
    roi_model.computed = roi_calc.compute(updated)
    roi_model.version += 1
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="roi.assumptions_edited", resource_type="opportunity",
          resource_id=opportunity_id, meta={"version": roi_model.version})
    return RoiOut(
        version=roi_model.version,
        assumptions=roi_model.assumptions,
        computed=roi_model.computed,
    )


# ---------- roadmap ----------


class RoadmapItemOut(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    horizon: RoadmapHorizon
    position: int
    quick_win: bool
    rationale: str
    depends_on: list
    opportunity: OpportunityOut | None = None

    model_config = {"from_attributes": True}


class RoadmapOut(BaseModel):
    horizons: dict[str, list[RoadmapItemOut]]


@router.post(
    "/orgs/{org_id}/projects/{project_id}/roadmap/generate",
    response_model=RoadmapOut,
)
def generate_roadmap(project_id: uuid.UUID, ctx: OrgCtx) -> RoadmapOut:
    """Deterministic sequencing over scored opportunities: horizon rules,
    quick-win rule, and integration-before-automation dependencies. The
    roadmap is derived state — regeneration replaces it; analyst judgments
    live on the opportunities themselves."""
    ctx.require_role(Role.analyst)
    opportunities = list(
        ctx.db.execute(
            select(Opportunity).where(
                Opportunity.project_id == project_id,
                Opportunity.review_state != ReviewState.rejected,
            )
        ).scalars()
    )
    if not opportunities:
        raise AppError("No opportunities to sequence; generate opportunities first")

    ctx.db.execute(delete(RoadmapItem).where(RoadmapItem.project_id == project_id))

    # Dependency rule: automation on a process waits for that process's
    # system integration (you don't robotize a swivel-chair you're deleting).
    integration_by_process: dict[uuid.UUID, Opportunity] = {
        o.process_id: o
        for o in opportunities
        if o.process_id
        and o.taxonomy_type == OpportunityTaxonomy.system_integration
    }
    dependent_types = {OpportunityTaxonomy.rpa, OpportunityTaxonomy.workflow_automation}

    items: list[RoadmapItem] = []
    for opportunity in opportunities:
        horizon = rubric.horizon_for(
            opportunity.impact_score, opportunity.complexity_score,
            opportunity.risk_score,
        )
        depends_on = []
        if (
            opportunity.taxonomy_type in dependent_types
            and opportunity.process_id in integration_by_process
            and integration_by_process[opportunity.process_id].id != opportunity.id
        ):
            dependency = integration_by_process[opportunity.process_id]
            depends_on = [str(dependency.id)]
            dep_horizon = rubric.horizon_for(
                dependency.impact_score, dependency.complexity_score,
                dependency.risk_score,
            )
            if int(horizon) <= int(dep_horizon):
                horizon = {"30": "90", "90": "180", "180": "365", "365": "365"}[
                    dep_horizon
                ]
        quick_win = rubric.is_quick_win(
            opportunity.impact_score, opportunity.complexity_score
        )
        items.append(
            RoadmapItem(
                org_id=ctx.org_id,
                project_id=project_id,
                opportunity_id=opportunity.id,
                horizon=RoadmapHorizon(horizon),
                quick_win=quick_win,
                rationale=(
                    f"Impact {opportunity.impact_score}, complexity "
                    f"{opportunity.complexity_score}, risk {opportunity.risk_score}"
                    + (" — quick win" if quick_win else "")
                    + (" — sequenced after prerequisite integration" if depends_on else "")
                ),
                depends_on=depends_on,
            )
        )

    by_horizon: dict[str, list[RoadmapItem]] = defaultdict(list)
    for item in items:
        by_horizon[item.horizon.value].append(item)
    for horizon_items in by_horizon.values():
        horizon_items.sort(key=lambda i: -next(
            o.impact_score for o in opportunities if o.id == i.opportunity_id
        ))
        for position, item in enumerate(horizon_items):
            item.position = position
            ctx.db.add(item)
    ctx.db.flush()
    audit(ctx.db, org_id=ctx.org_id, actor_id=ctx.user.id,
          action="roadmap.generated", resource_type="project", resource_id=project_id,
          meta={"items": len(items)})
    return _roadmap_out(ctx, project_id)


@router.get("/orgs/{org_id}/projects/{project_id}/roadmap", response_model=RoadmapOut)
def get_roadmap(project_id: uuid.UUID, ctx: OrgCtx) -> RoadmapOut:
    return _roadmap_out(ctx, project_id)


def _roadmap_out(ctx: OrgCtx, project_id: uuid.UUID) -> RoadmapOut:
    items = list(
        ctx.db.execute(
            select(RoadmapItem)
            .where(RoadmapItem.project_id == project_id)
            .order_by(RoadmapItem.horizon, RoadmapItem.position)
        ).scalars()
    )
    opportunity_ids = [i.opportunity_id for i in items]
    opportunities = []
    if opportunity_ids:
        opportunities = list(
            ctx.db.execute(
                select(Opportunity).where(Opportunity.id.in_(opportunity_ids))
            ).scalars()
        )
    hydrated = {o.id: o for o in _hydrate(ctx, opportunities)}
    horizons: dict[str, list[RoadmapItemOut]] = {"30": [], "90": [], "180": [], "365": []}
    for item in items:
        view = RoadmapItemOut.model_validate(item)
        view.opportunity = hydrated.get(item.opportunity_id)
        horizons[item.horizon.value].append(view)
    return RoadmapOut(horizons=horizons)
