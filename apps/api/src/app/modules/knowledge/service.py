"""PKM write path and review operations.

The evidence invariant lives here: `create_entity`/`create_relation`
refuse assertions without evidence unless explicitly flagged as an
estimate. Review operations record history and resolve queue items.
"""

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.modules.knowledge.models import (
    ENTITY_TYPES,
    RELATION_TYPES,
    Confidence,
    Entity,
    EntityHistory,
    EntityRelation,
    Evidence,
    ReviewItem,
    ReviewItemKind,
    ReviewState,
)


class EvidenceInvariantError(AppError):
    code = "evidence_required"


@dataclass
class EvidenceRef:
    element_id: uuid.UUID
    document_id: uuid.UUID
    quote: str | None = None


@dataclass
class ExtractedItem:
    """What extractors emit — the service turns these into PKM rows."""

    type: str
    name: str
    confidence: Confidence
    evidence: list[EvidenceRef]
    attrs: dict = field(default_factory=dict)
    novel: bool = False


def canonicalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def create_entity(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    item: ExtractedItem,
    source: str = "pipeline",
    estimate: bool = False,
) -> Entity:
    if item.type not in ENTITY_TYPES:
        raise AppError(f"Unknown entity type: {item.type}")
    if not item.evidence and not estimate:
        raise EvidenceInvariantError(
            f"Entity '{item.name}' asserted without evidence (docs/04)"
        )
    entity = Entity(
        org_id=org_id,
        project_id=project_id,
        type=item.type,
        name=item.name,
        canonical_name=canonicalize(item.name),
        attrs={**item.attrs, **({"estimate": True} if estimate else {})},
        confidence=item.confidence,
        novel=item.novel,
        source=source,
    )
    session.add(entity)
    session.flush()
    _add_evidence(session, org_id, "entity", entity.id, item.evidence)

    if item.confidence != Confidence.high:
        session.add(
            ReviewItem(
                org_id=org_id,
                project_id=project_id,
                kind=ReviewItemKind.low_confidence,
                subject_type="entity",
                subject_id=entity.id,
                question=(
                    f'Is "{item.name}" a real {item.type.replace("_", " ")} '
                    f"in this operation?"
                ),
            )
        )
    return entity


def create_relation(
    session: Session,
    *,
    org_id: uuid.UUID,
    project_id: uuid.UUID,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    rel_type: str,
    confidence: Confidence,
    evidence: list[EvidenceRef],
    attrs: dict | None = None,
) -> EntityRelation:
    if rel_type not in RELATION_TYPES:
        raise AppError(f"Unknown relation type: {rel_type}")
    if not evidence:
        raise EvidenceInvariantError(f"Relation '{rel_type}' asserted without evidence")
    relation = EntityRelation(
        org_id=org_id,
        project_id=project_id,
        from_id=from_id,
        to_id=to_id,
        rel_type=rel_type,
        confidence=confidence,
        attrs=attrs or {},
    )
    session.add(relation)
    session.flush()
    _add_evidence(session, org_id, "relation", relation.id, evidence)
    return relation


def _add_evidence(
    session: Session,
    org_id: uuid.UUID,
    claimable_type: str,
    claimable_id: uuid.UUID,
    refs: list[EvidenceRef],
) -> None:
    for ref in refs:
        session.add(
            Evidence(
                org_id=org_id,
                claimable_type=claimable_type,
                claimable_id=claimable_id,
                element_id=ref.element_id,
                document_id=ref.document_id,
                quote=(ref.quote or "")[:500] or None,
            )
        )


def review_entity(
    session: Session,
    *,
    entity: Entity,
    action: str,
    user_id: uuid.UUID,
    edits: dict | None = None,
) -> Entity:
    """confirm | reject | edit — records history; corrections are eval data."""
    before = {"name": entity.name, "attrs": entity.attrs,
              "review_state": entity.review_state.value}
    if action == "confirm":
        entity.review_state = ReviewState.confirmed
    elif action == "reject":
        entity.review_state = ReviewState.rejected
    elif action == "edit":
        if edits and "name" in edits:
            entity.name = str(edits["name"])[:300]
            entity.canonical_name = canonicalize(entity.name)
        if edits and "attrs" in edits and isinstance(edits["attrs"], dict):
            entity.attrs = {**entity.attrs, **edits["attrs"]}
        entity.review_state = ReviewState.edited
    else:
        raise AppError(f"Unknown review action: {action}")
    entity.version += 1
    session.add(
        EntityHistory(
            org_id=entity.org_id,
            entity_id=entity.id,
            change_source="analyst",
            changed_by=user_id,
            before=before,
            after={"name": entity.name, "attrs": entity.attrs,
                   "review_state": entity.review_state.value},
        )
    )
    # Auto-resolve the low-confidence question tied to this entity, if open.
    open_items = session.execute(
        select(ReviewItem).where(
            ReviewItem.subject_type == "entity",
            ReviewItem.subject_id == entity.id,
            ReviewItem.status == "open",
            ReviewItem.kind == ReviewItemKind.low_confidence,
        )
    ).scalars()
    for review_item in open_items:
        review_item.status = "resolved"  # type: ignore[assignment]
        review_item.resolved_by = user_id
        review_item.resolution = {"via": f"entity_{action}"}
    session.flush()
    return entity


def merge_entities(
    session: Session, *, keep: Entity, merge: Entity, user_id: uuid.UUID
) -> Entity:
    """Merge `merge` into `keep`: relations and evidence are repointed, the
    merged entity is rejected (not deleted — history stays walkable)."""
    for relation in session.execute(
        select(EntityRelation).where(
            (EntityRelation.from_id == merge.id) | (EntityRelation.to_id == merge.id)
        )
    ).scalars():
        if relation.from_id == merge.id:
            relation.from_id = keep.id
        if relation.to_id == merge.id:
            relation.to_id = keep.id
    for evidence in session.execute(
        select(Evidence).where(
            Evidence.claimable_type == "entity", Evidence.claimable_id == merge.id
        )
    ).scalars():
        evidence.claimable_id = keep.id
    aliases = set(keep.attrs.get("aliases", []))
    aliases.add(merge.name)
    keep.attrs = {**keep.attrs, "aliases": sorted(aliases)}
    merge.review_state = ReviewState.rejected
    merge.attrs = {**merge.attrs, "merged_into": str(keep.id)}
    session.add(
        EntityHistory(
            org_id=keep.org_id,
            entity_id=keep.id,
            change_source="analyst",
            changed_by=user_id,
            before=None,
            after={"merged": str(merge.id), "alias_added": merge.name},
        )
    )
    session.flush()
    return keep
