"""Project-level knowledge extraction pipeline (docs/06 M2).

extract → resolve → finalize. Re-runs are safe: the extract step clears
only prior *pipeline-generated, unreviewed* output — anything the analyst
confirmed, edited, or rejected is never touched by a machine pass.
"""

import re
import uuid
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.extract import get_extractor
from app.logging import get_logger
from app.modules.documents.elements import DocumentElement
from app.modules.documents.models import Document, DocumentStatus
from app.modules.knowledge.models import (
    Confidence,
    Entity,
    EntityRelation,
    Evidence,
    ReviewItem,
    ReviewItemKind,
    ReviewState,
)
from app.modules.knowledge.service import (
    EvidenceRef,
    ExtractedItem,
    canonicalize,
    create_entity,
    create_relation,
)
from app.worker.runner import StepContext

log = get_logger("knowledge")


def _clear_unreviewed(session: Session, project_id: uuid.UUID) -> None:
    entity_ids = [
        row[0]
        for row in session.execute(
            select(Entity.id).where(
                Entity.project_id == project_id,
                Entity.source == "pipeline",
                Entity.review_state == ReviewState.ai_generated,
            )
        )
    ]
    if not entity_ids:
        return
    relation_ids = [
        row[0]
        for row in session.execute(
            select(EntityRelation.id).where(
                EntityRelation.from_id.in_(entity_ids)
                | EntityRelation.to_id.in_(entity_ids)
            )
        )
    ]
    # Evidence is a polymorphic link (no FK cascade) — clear it explicitly.
    session.execute(
        delete(Evidence).where(
            Evidence.claimable_type == "entity", Evidence.claimable_id.in_(entity_ids)
        )
    )
    if relation_ids:
        session.execute(
            delete(Evidence).where(
                Evidence.claimable_type == "relation",
                Evidence.claimable_id.in_(relation_ids),
            )
        )
    session.execute(
        delete(ReviewItem).where(
            ReviewItem.subject_type == "entity",
            ReviewItem.subject_id.in_(entity_ids),
            ReviewItem.status == "open",
        )
    )
    session.execute(delete(Entity).where(Entity.id.in_(entity_ids)))
    session.flush()


def extract_knowledge(session: Session, ctx: StepContext) -> tuple[dict, int]:
    run = ctx.run
    _clear_unreviewed(session, run.project_id)

    documents = (
        session.execute(
            select(Document).where(
                Document.project_id == run.project_id,
                Document.status == DocumentStatus.ready,
                Document.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    extractor = get_extractor()
    # Cross-document dedupe: one entity per (type, canonical name) per project.
    registry: dict[tuple[str, str], Entity] = {
        (e.type, e.canonical_name): e
        for e in session.execute(
            select(Entity).where(Entity.project_id == run.project_id)
        ).scalars()
        if e.review_state != ReviewState.rejected
    }

    def upsert(item: ExtractedItem) -> Entity:
        key = (item.type, canonicalize(item.name))
        existing = registry.get(key)
        if existing is not None:
            for ref in item.evidence:
                session.add(
                    Evidence(
                        org_id=run.org_id,
                        claimable_type="entity",
                        claimable_id=existing.id,
                        element_id=ref.element_id,
                        document_id=ref.document_id,
                        quote=(ref.quote or "")[:500] or None,
                    )
                )
            return existing
        entity = create_entity(
            session, org_id=run.org_id, project_id=run.project_id,
            item=item, source="pipeline",
        )
        registry[key] = entity
        return entity

    entity_count = 0
    relation_count = 0
    for doc in documents:
        elements = list(
            session.execute(
                select(DocumentElement)
                .where(DocumentElement.document_id == doc.id)
                .order_by(DocumentElement.order_key)
            ).scalars()
        )
        if not elements:
            continue
        output = extractor.extract(doc, elements)
        doc_pain_points: list[Entity] = []
        for item in output.items:
            entity = upsert(item)
            entity_count += 1
            if item.type == "pain_point":
                doc_pain_points.append(entity)

        for process_item, step_items in output.processes:
            process = upsert(process_item)
            previous: Entity | None = None
            for step_item in step_items:
                step = upsert(step_item)
                create_relation(
                    session, org_id=run.org_id, project_id=run.project_id,
                    from_id=step.id, to_id=process.id, rel_type="part_of",
                    confidence=Confidence.medium, evidence=step_item.evidence,
                )
                if previous is not None:
                    create_relation(
                        session, org_id=run.org_id, project_id=run.project_id,
                        from_id=previous.id, to_id=step.id, rel_type="precedes",
                        confidence=Confidence.medium, evidence=step_item.evidence,
                    )
                    relation_count += 1
                performer = step_item.attrs.get("performer")
                if performer:
                    actor = registry.get(("actor", canonicalize(performer)))
                    if actor is not None:
                        create_relation(
                            session, org_id=run.org_id, project_id=run.project_id,
                            from_id=actor.id, to_id=step.id, rel_type="performs",
                            confidence=Confidence.medium, evidence=step_item.evidence,
                        )
                for system_name in step_item.attrs.get("systems", []):
                    system = registry.get(("system", canonicalize(system_name)))
                    if system is not None:
                        create_relation(
                            session, org_id=run.org_id, project_id=run.project_id,
                            from_id=step.id, to_id=system.id, rel_type="uses_system",
                            confidence=Confidence.medium, evidence=step_item.evidence,
                        )
                previous = step
            # Pain points found in the same document affect this process.
            for pain in doc_pain_points:
                pain_evidence = [
                    EvidenceRef(ev.element_id, ev.document_id, ev.quote)
                    for ev in session.execute(
                        select(Evidence).where(
                            Evidence.claimable_type == "entity",
                            Evidence.claimable_id == pain.id,
                        ).limit(1)
                    ).scalars()
                ]
                if pain_evidence:
                    create_relation(
                        session, org_id=run.org_id, project_id=run.project_id,
                        from_id=pain.id, to_id=process.id, rel_type="affects",
                        confidence=Confidence.medium, evidence=pain_evidence,
                    )

    session.flush()
    return {
        "documents": len(documents),
        "entities": entity_count,
        "relations": relation_count,
        "extractor": extractor.name,
    }, 0


def _tokens(canonical: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", canonical))


def resolve_entities(session: Session, ctx: StepContext) -> tuple[dict, int]:
    """Propose merges for suspiciously-similar names; ambiguity becomes an
    analyst question, never a silent merge (docs/03 §3)."""
    run = ctx.run
    entities = list(
        session.execute(
            select(Entity).where(
                Entity.project_id == run.project_id,
                Entity.review_state != ReviewState.rejected,
            )
        ).scalars()
    )
    existing_pairs = {
        frozenset({str(item.subject_id), item.payload.get("other_id", "")})
        for item in session.execute(
            select(ReviewItem).where(
                ReviewItem.project_id == run.project_id,
                ReviewItem.kind == ReviewItemKind.merge_proposal,
            )
        ).scalars()
    }
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_type[entity.type].append(entity)

    proposals = 0
    for entity_type, group in by_type.items():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                ta, tb = _tokens(a.canonical_name), _tokens(b.canonical_name)
                if not ta or not tb:
                    continue
                overlap = len(ta & tb) / len(ta | tb)
                contained = ta <= tb or tb <= ta
                # Role names sharing a head noun ("Intake Supervisor" /
                # "Claims Supervisor") are a classic same-or-different call
                # only the analyst can make — ask.
                shared_head = (
                    entity_type == "actor"
                    and a.canonical_name.split()[-1] == b.canonical_name.split()[-1]
                )
                if not (contained or overlap >= 0.5 or shared_head):
                    continue
                if frozenset({str(a.id), str(b.id)}) in existing_pairs:
                    continue
                session.add(
                    ReviewItem(
                        org_id=run.org_id,
                        project_id=run.project_id,
                        kind=ReviewItemKind.merge_proposal,
                        subject_type="entity",
                        subject_id=a.id,
                        question=(
                            f'Are "{a.name}" and "{b.name}" the same '
                            f"{a.type.replace('_', ' ')}?"
                        ),
                        payload={"other_id": str(b.id), "other_name": b.name},
                    )
                )
                existing_pairs.add(frozenset({str(a.id), str(b.id)}))
                proposals += 1
    session.flush()
    return {"merge_proposals": proposals}, 0


def finalize_knowledge(session: Session, ctx: StepContext) -> tuple[dict, int]:
    counts: dict[str, int] = defaultdict(int)
    for entity in session.execute(
        select(Entity).where(Entity.project_id == ctx.run.project_id)
    ).scalars():
        counts[entity.type] += 1
    return dict(counts), 0
