"""Deliverable spec builders (docs/03 §5).

A spec is the complete structured content of a deliverable: sections,
tables, figures, and a numbered citation registry. Renderers are pure
functions of the spec — if a number or claim isn't in the spec, it cannot
appear in an export. Quantities come only from ROI sheets (computed in
code); claims carry citation indexes; unreviewed content is marked so
renderers can label it.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.deliverables.models import DeliverableType
from app.modules.documents.models import Document, DocumentStatus
from app.modules.knowledge.models import Entity, EntityRelation, Evidence, ReviewState
from app.modules.opportunities.models import Opportunity, RoadmapItem, RoiModel
from app.modules.projects.models import Project

GENERATOR_VERSION = "1"


class _Citations:
    """Numbered, de-duplicated citation registry for one spec."""

    def __init__(self, session: Session):
        self._session = session
        self._by_element: dict[uuid.UUID, int] = {}
        self.entries: list[dict] = []
        self._filenames: dict[uuid.UUID, str] = {}

    def _filename(self, document_id: uuid.UUID) -> str:
        if document_id not in self._filenames:
            doc = self._session.get(Document, document_id)
            self._filenames[document_id] = doc.filename if doc else "unknown"
        return self._filenames[document_id]

    def add_for(self, claimable_type: str, claimable_id: uuid.UUID) -> list[int]:
        rows = self._session.execute(
            select(Evidence).where(
                Evidence.claimable_type == claimable_type,
                Evidence.claimable_id == claimable_id,
            ).limit(3)
        ).scalars()
        numbers = []
        for evidence in rows:
            if evidence.element_id in self._by_element:
                numbers.append(self._by_element[evidence.element_id])
                continue
            n = len(self.entries) + 1
            self._by_element[evidence.element_id] = n
            self.entries.append(
                {
                    "n": n,
                    "document_id": str(evidence.document_id),
                    "element_id": str(evidence.element_id),
                    "filename": self._filename(evidence.document_id),
                    "quote": evidence.quote,
                }
            )
            numbers.append(n)
        return numbers


def _knowledge(session: Session, project_id: uuid.UUID):
    entities = list(
        session.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.review_state != ReviewState.rejected,
            )
        ).scalars()
    )
    by_type: dict[str, list[Entity]] = defaultdict(list)
    for entity in entities:
        by_type[entity.type].append(entity)
    # Analyst-validated first, then by confidence.
    rank = {ReviewState.confirmed: 0, ReviewState.edited: 0, ReviewState.ai_generated: 1}
    for group in by_type.values():
        group.sort(key=lambda e: (rank[e.review_state], e.name))
    return entities, by_type


def _review_coverage(entities: list[Entity]) -> str:
    if not entities:
        return "0%"
    reviewed = sum(
        1 for e in entities
        if e.review_state in (ReviewState.confirmed, ReviewState.edited)
    )
    return f"{round(100 * reviewed / len(entities))}%"


def _opportunities(session: Session, project_id: uuid.UUID):
    opportunities = list(
        session.execute(
            select(Opportunity)
            .where(
                Opportunity.project_id == project_id,
                Opportunity.review_state != ReviewState.rejected,
            )
            .order_by(Opportunity.impact_score.desc(), Opportunity.complexity_score)
        ).scalars()
    )
    roi_by_id: dict[uuid.UUID, RoiModel] = {
        r.opportunity_id: r
        for r in session.execute(
            select(RoiModel).where(
                RoiModel.opportunity_id.in_([o.id for o in opportunities])
            )
        ).scalars()
    } if opportunities else {}
    return opportunities, roi_by_id


def _unreviewed(state: ReviewState) -> bool:
    return state == ReviewState.ai_generated


def build_spec(
    session: Session, project: Project, deliverable_type: DeliverableType
) -> dict:
    citations = _Citations(session)
    entities, by_type = _knowledge(session, project.id)
    opportunities, roi_by_id = _opportunities(session, project.id)
    doc_count = session.execute(
        select(Document).where(
            Document.project_id == project.id,
            Document.status == DocumentStatus.ready,
        )
    ).scalars().all()

    sections: list[dict]
    if deliverable_type == DeliverableType.executive_summary:
        sections = _executive_summary_sections(
            by_type, opportunities, roi_by_id, len(doc_count), entities, citations,
            session, project.id,
        )
        title = f"Executive Summary — {project.name}"
    elif deliverable_type == DeliverableType.current_state_assessment:
        sections = _assessment_sections(session, project.id, by_type, citations)
        title = f"Current-State Assessment — {project.name}"
    elif deliverable_type == DeliverableType.opportunity_register:
        sections = _register_sections(opportunities, roi_by_id, citations)
        title = f"Opportunity Register — {project.name}"
    else:
        sections = _roadmap_sections(session, project.id, opportunities, roi_by_id)
        title = f"Transformation Roadmap — {project.name}"

    return {
        "type": deliverable_type.value,
        "title": title,
        "project_name": project.name,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "review_coverage": _review_coverage(entities),
        "sections": sections,
        "citations": citations.entries,
    }


def _executive_summary_sections(
    by_type, opportunities, roi_by_id, doc_count, entities, citations, session, project_id
) -> list[dict]:
    pains = by_type.get("pain_point", [])
    taxonomy_counts: dict[str, int] = defaultdict(int)
    for pain in pains:
        taxonomy_counts[(pain.attrs or {}).get("taxonomy", "other")] += 1

    total_net = sum(
        (roi_by_id[o.id].computed.get("net_annual_savings") or 0)
        for o in opportunities
        if o.id in roi_by_id
    )
    stats = [
        {"label": "Documents analyzed", "value": str(doc_count)},
        {"label": "Processes mapped", "value": str(len(by_type.get("process", [])))},
        {"label": "Pain points identified", "value": str(len(pains))},
        {"label": "Opportunities scored", "value": str(len(opportunities))},
        {"label": "Net annual savings (modeled)", "value": f"${total_net:,.0f}"},
        {"label": "Model analyst-reviewed", "value": _review_coverage(entities)},
    ]

    findings = []
    for pain in pains[:8]:
        findings.append(
            {
                "text": pain.name,
                "taxonomy": (pain.attrs or {}).get("taxonomy"),
                "unreviewed": _unreviewed(pain.review_state),
                "citations": citations.add_for("entity", pain.id),
            }
        )

    opportunity_rows = []
    for opportunity in opportunities[:8]:
        roi = roi_by_id.get(opportunity.id)
        opportunity_rows.append(
            {
                "title": opportunity.title,
                "taxonomy": opportunity.taxonomy_type.value,
                "impact": opportunity.impact_score,
                "complexity": opportunity.complexity_score,
                "risk": opportunity.risk_score,
                "net_annual_savings": (
                    roi.computed.get("net_annual_savings") if roi else None
                ),
                "payback_months": roi.computed.get("payback_months") if roi else None,
                "unreviewed": _unreviewed(opportunity.review_state),
                "citations": citations.add_for("opportunity", opportunity.id),
            }
        )

    return [
        {
            "kind": "overview",
            "heading": "Engagement overview",
            "body": (
                "This summary was generated from the project's evidence-linked "
                "knowledge model. Every finding cites its source document; every "
                "financial figure derives from an editable assumption sheet."
            ),
            "stats": stats,
        },
        {"kind": "findings", "heading": "Key findings", "items": findings},
        {
            "kind": "opportunities",
            "heading": "Top opportunities",
            "rows": opportunity_rows,
        },
        _roadmap_summary_section(session, project_id),
    ]


def _roadmap_summary_section(session: Session, project_id: uuid.UUID) -> dict:
    items = list(
        session.execute(
            select(RoadmapItem)
            .where(RoadmapItem.project_id == project_id)
            .order_by(RoadmapItem.horizon, RoadmapItem.position)
        ).scalars()
    )
    titles: dict[uuid.UUID, str] = {}
    if items:
        for opportunity in session.execute(
            select(Opportunity).where(
                Opportunity.id.in_([i.opportunity_id for i in items])
            )
        ).scalars():
            titles[opportunity.id] = opportunity.title
    horizons: dict[str, list[dict]] = {"30": [], "90": [], "180": [], "365": []}
    for item in items:
        horizons[item.horizon.value].append(
            {
                "title": titles.get(item.opportunity_id, "Opportunity"),
                "quick_win": item.quick_win,
            }
        )
    return {"kind": "roadmap", "heading": "Roadmap", "horizons": horizons}


def _assessment_sections(session, project_id, by_type, citations) -> list[dict]:
    sections: list[dict] = [
        {
            "kind": "table",
            "heading": "Actors",
            "columns": ["Actor", "Review state"],
            "rows": [
                [a.name, a.review_state.value.replace("_", " ")]
                for a in by_type.get("actor", [])
            ],
        },
        {
            "kind": "table",
            "heading": "Systems",
            "columns": ["System", "Review state"],
            "rows": [
                [s.name, s.review_state.value.replace("_", " ")]
                for s in by_type.get("system", [])
            ],
        },
    ]

    relations = list(
        session.execute(
            select(EntityRelation).where(EntityRelation.project_id == project_id)
        ).scalars()
    )
    step_to_process = {
        r.from_id: r.to_id for r in relations if r.rel_type == "part_of"
    }
    performer = {}
    entity_names = {e.id: e for group in by_type.values() for e in group}
    for relation in relations:
        if relation.rel_type == "performs" and relation.from_id in entity_names:
            performer[relation.to_id] = entity_names[relation.from_id].name

    for process in by_type.get("process", []):
        steps = sorted(
            (
                e for e in by_type.get("process_step", [])
                if step_to_process.get(e.id) == process.id
            ),
            key=lambda e: (e.attrs or {}).get("order", 0),
        )
        pains = [
            entity_names[r.from_id]
            for r in relations
            if r.rel_type == "affects" and r.to_id == process.id
            and r.from_id in entity_names
        ]
        sections.append(
            {
                "kind": "process",
                "heading": f"Process: {process.name}",
                "unreviewed": _unreviewed(process.review_state),
                "citations": citations.add_for("entity", process.id),
                "steps": [
                    {
                        "order": (s.attrs or {}).get("order", 0) + 1,
                        "name": s.name,
                        "step_type": (s.attrs or {}).get("step_type", "system"),
                        "performer": performer.get(s.id, "—"),
                        "unreviewed": _unreviewed(s.review_state),
                        "citations": citations.add_for("entity", s.id),
                    }
                    for s in steps
                ],
                "pain_points": [
                    {
                        "text": p.name,
                        "taxonomy": (p.attrs or {}).get("taxonomy"),
                        "unreviewed": _unreviewed(p.review_state),
                        "citations": citations.add_for("entity", p.id),
                    }
                    for p in pains
                ],
            }
        )

    rules = by_type.get("business_rule", [])
    if rules:
        sections.append(
            {
                "kind": "findings",
                "heading": "Business rules and obligations",
                "items": [
                    {
                        "text": rule.name,
                        "taxonomy": None,
                        "unreviewed": _unreviewed(rule.review_state),
                        "citations": citations.add_for("entity", rule.id),
                    }
                    for rule in rules[:15]
                ],
            }
        )
    return sections


def _register_sections(opportunities, roi_by_id, citations) -> list[dict]:
    rows = []
    assumption_rows = []
    for opportunity in opportunities:
        roi = roi_by_id.get(opportunity.id)
        rows.append(
            {
                "title": opportunity.title,
                "taxonomy": opportunity.taxonomy_type.value,
                "impact": opportunity.impact_score,
                "complexity": opportunity.complexity_score,
                "risk": opportunity.risk_score,
                "rationale": opportunity.rationale,
                "net_annual_savings": (
                    roi.computed.get("net_annual_savings") if roi else None
                ),
                "payback_months": roi.computed.get("payback_months") if roi else None,
                "three_year_net": roi.computed.get("three_year_net") if roi else None,
                "unreviewed": _unreviewed(opportunity.review_state),
                "citations": citations.add_for("opportunity", opportunity.id),
            }
        )
        if roi:
            for assumption in roi.assumptions:
                assumption_rows.append(
                    [
                        opportunity.title,
                        assumption["label"],
                        assumption["value"],
                        assumption["unit"],
                        assumption["source"],
                    ]
                )
    return [
        {"kind": "opportunities", "heading": "Opportunity register", "rows": rows},
        {
            "kind": "table",
            "heading": "ROI assumptions",
            "columns": ["Opportunity", "Assumption", "Value", "Unit", "Source"],
            "rows": assumption_rows,
        },
    ]


def _roadmap_sections(session, project_id, opportunities, roi_by_id) -> list[dict]:
    roadmap = _roadmap_summary_section(session, project_id)
    total_net = sum(
        (roi_by_id[o.id].computed.get("net_annual_savings") or 0)
        for o in opportunities
        if o.id in roi_by_id
    )
    return [
        {
            "kind": "overview",
            "heading": "Transformation roadmap",
            "body": (
                "Sequencing follows explicit rules: quick wins first "
                "(impact ≥ 3, complexity ≤ 2), and automation is scheduled "
                "after its prerequisite integration."
            ),
            "stats": [
                {"label": "Initiatives", "value": str(len(opportunities))},
                {
                    "label": "Net annual savings (modeled)",
                    "value": f"${total_net:,.0f}",
                },
            ],
        },
        roadmap,
    ]
