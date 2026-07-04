"""opportunity_generate pipeline: generate → propose_roi → finalize.

Re-runs clear only pipeline-generated, unreviewed opportunities; anything
the analyst confirmed, edited, or rejected survives (same contract as
knowledge extraction).
"""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.modules.knowledge.models import Evidence, ReviewState
from app.modules.opportunities import roi
from app.modules.opportunities.generator import generate_opportunities
from app.modules.opportunities.models import Opportunity, RoadmapItem, RoiModel
from app.worker.runner import StepContext


def _clear_unreviewed(session: Session, project_id: uuid.UUID) -> None:
    ids = [
        row[0]
        for row in session.execute(
            select(Opportunity.id).where(
                Opportunity.project_id == project_id,
                Opportunity.source == "pipeline",
                Opportunity.review_state == ReviewState.ai_generated,
            )
        )
    ]
    if not ids:
        return
    session.execute(
        delete(Evidence).where(
            Evidence.claimable_type == "opportunity", Evidence.claimable_id.in_(ids)
        )
    )
    session.execute(delete(RoiModel).where(RoiModel.opportunity_id.in_(ids)))
    session.execute(delete(RoadmapItem).where(RoadmapItem.opportunity_id.in_(ids)))
    session.execute(delete(Opportunity).where(Opportunity.id.in_(ids)))
    session.flush()


def generate(session: Session, ctx: StepContext) -> tuple[dict, int]:
    run = ctx.run
    _clear_unreviewed(session, run.project_id)
    created = generate_opportunities(
        session, org_id=run.org_id, project_id=run.project_id
    )
    ctx.outputs["generated_ids"] = {"ids": [str(o.id) for o in created]}
    return {"opportunities": len(created)}, 0


def propose_roi(session: Session, ctx: StepContext) -> tuple[dict, int]:
    run = ctx.run
    opportunities = list(
        session.execute(
            select(Opportunity).where(Opportunity.project_id == run.project_id)
        ).scalars()
    )
    proposed = 0
    for opportunity in opportunities:
        existing = session.execute(
            select(RoiModel).where(RoiModel.opportunity_id == opportunity.id)
        ).scalar_one_or_none()
        if existing is not None:
            continue  # never overwrite an analyst's assumption sheet
        assumptions = roi.propose_assumptions(opportunity.taxonomy_type)
        session.add(
            RoiModel(
                org_id=run.org_id,
                opportunity_id=opportunity.id,
                assumptions=assumptions,
                computed=roi.compute(assumptions),
            )
        )
        proposed += 1
    session.flush()
    return {"roi_models_proposed": proposed}, 0


def finalize(session: Session, ctx: StepContext) -> tuple[dict, int]:
    count = len(
        session.execute(
            select(Opportunity.id).where(Opportunity.project_id == ctx.run.project_id)
        ).all()
    )
    return {"total_opportunities": count}, 0
