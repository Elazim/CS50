"""Opportunity generation from the validated knowledge model (docs/03 §5).

Every opportunity binds to specific pain points and inherits their
evidence — "adopt AI chatbots" with no citation cannot exist here by
construction. Generation is deterministic given the PKM and rubric
version; an LLM narrative pass can later enrich descriptions behind the
same structure without touching scoring.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.knowledge.models import Entity, EntityRelation, Evidence, ReviewState
from app.modules.opportunities import rubric
from app.modules.opportunities.models import Opportunity, OpportunityTaxonomy

_TITLES: dict[OpportunityTaxonomy, str] = {
    OpportunityTaxonomy.system_integration: "Integrate systems to eliminate rekeying",
    OpportunityTaxonomy.rpa: "Robotic automation of repetitive entry",
    OpportunityTaxonomy.workflow_automation: "Automate workflow and handoffs",
    OpportunityTaxonomy.document_ai: "Document AI for manual document handling",
    OpportunityTaxonomy.decision_engine: "Rules-based routing and assignment",
    OpportunityTaxonomy.generative_ai: "Generative AI assistance",
    OpportunityTaxonomy.knowledge_search: "Knowledge search over operational documents",
    OpportunityTaxonomy.process_redesign: "Process redesign",
    OpportunityTaxonomy.elimination: "Eliminate redundant work",
}


@dataclass
class ProcessContext:
    process: Entity | None
    pain_points: list[Entity]
    step_count: int
    systems_involved: int
    has_compliance_context: bool


def build_contexts(session: Session, project_id: uuid.UUID) -> list[ProcessContext]:
    entities = list(
        session.execute(
            select(Entity).where(
                Entity.project_id == project_id,
                Entity.review_state != ReviewState.rejected,
            )
        ).scalars()
    )
    by_id = {e.id: e for e in entities}
    relations = list(
        session.execute(
            select(EntityRelation).where(EntityRelation.project_id == project_id)
        ).scalars()
    )

    pains_by_process: dict[uuid.UUID, list[Entity]] = defaultdict(list)
    steps_by_process: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    systems_by_process: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    linked_pains: set[uuid.UUID] = set()

    step_to_process: dict[uuid.UUID, uuid.UUID] = {}
    for relation in relations:
        if relation.rel_type == "part_of":
            steps_by_process[relation.to_id].add(relation.from_id)
            step_to_process[relation.from_id] = relation.to_id
    for relation in relations:
        if relation.rel_type == "affects":
            pain = by_id.get(relation.from_id)
            if pain is None or pain.type != "pain_point":
                continue
            target_process = (
                relation.to_id
                if relation.to_id in steps_by_process
                else step_to_process.get(relation.to_id)
            )
            if target_process:
                pains_by_process[target_process].append(pain)
                linked_pains.add(pain.id)
        if relation.rel_type == "uses_system":
            process_id = step_to_process.get(relation.from_id)
            if process_id:
                systems_by_process[process_id].add(relation.to_id)

    rule_count = sum(1 for e in entities if e.type in ("business_rule", "compliance_item"))
    contexts = [
        ProcessContext(
            process=by_id[process_id],
            pain_points=pains,
            step_count=len(steps_by_process.get(process_id, ())),
            systems_involved=len(systems_by_process.get(process_id, ())),
            has_compliance_context=rule_count > 0,
        )
        for process_id, pains in pains_by_process.items()
        if process_id in by_id
    ]

    orphan_pains = [
        e for e in entities if e.type == "pain_point" and e.id not in linked_pains
    ]
    if orphan_pains:
        contexts.append(
            ProcessContext(
                process=None,
                pain_points=orphan_pains,
                step_count=0,
                systems_involved=0,
                has_compliance_context=rule_count > 0,
            )
        )
    return contexts


def generate_opportunities(
    session: Session, *, org_id: uuid.UUID, project_id: uuid.UUID
) -> list[Opportunity]:
    created: list[Opportunity] = []
    for context in build_contexts(session, project_id):
        by_taxonomy: dict[str, list[Entity]] = defaultdict(list)
        for pain in context.pain_points:
            taxonomy = (pain.attrs or {}).get("taxonomy", "manual_work")
            by_taxonomy[taxonomy].append(pain)

        # One opportunity per mapped type; several waste types can converge
        # on the same intervention (rework + shadow_it → one integration).
        pains_by_type: dict[OpportunityTaxonomy, list[Entity]] = defaultdict(list)
        taxonomies_by_type: dict[OpportunityTaxonomy, set[str]] = defaultdict(set)
        for taxonomy, pains in by_taxonomy.items():
            options = rubric.TAXONOMY_TO_OPPORTUNITY.get(
                taxonomy, [OpportunityTaxonomy.process_redesign]
            )
            pains_by_type[options[0]].extend(pains)
            taxonomies_by_type[options[0]].add(taxonomy)

        for opp_type, pains in pains_by_type.items():
            impact = rubric.score_impact(
                len(pains), len(taxonomies_by_type[opp_type]), context.step_count
            )
            complexity = rubric.score_complexity(opp_type, context.systems_involved)
            risk = rubric.score_risk(opp_type, context.has_compliance_context)
            scope = context.process.name if context.process else "cross-cutting operations"
            rationale = (
                f"Addresses {len(pains)} documented pain point(s) "
                f"({', '.join(sorted(taxonomies_by_type[opp_type]))}) in {scope}. "
                f"Impact {impact}: {len(pains)} pain point(s) across "
                f"{context.step_count} step(s). Complexity {complexity}: base for "
                f"{opp_type.value} with {context.systems_involved} system(s) involved. "
                f"Risk {risk}."
            )
            opportunity = Opportunity(
                org_id=org_id,
                project_id=project_id,
                process_id=context.process.id if context.process else None,
                taxonomy_type=opp_type,
                title=f"{_TITLES[opp_type]} — {scope}"[:300],
                description=" ".join(
                    f"• {p.name}" for p in pains[:5]
                ),
                impact_score=impact,
                complexity_score=complexity,
                risk_score=risk,
                rationale=rationale,
                rubric_version=rubric.RUBRIC_VERSION,
                attrs={"pain_point_ids": [str(p.id) for p in pains]},
            )
            session.add(opportunity)
            session.flush()
            # Inherit the pain points' evidence: the citation chain extends
            # from source passage → pain point → opportunity.
            inherited = session.execute(
                select(Evidence).where(
                    Evidence.claimable_type == "entity",
                    Evidence.claimable_id.in_([p.id for p in pains]),
                )
            ).scalars()
            seen_elements = set()
            for evidence in inherited:
                if evidence.element_id in seen_elements:
                    continue
                seen_elements.add(evidence.element_id)
                session.add(
                    Evidence(
                        org_id=org_id,
                        claimable_type="opportunity",
                        claimable_id=opportunity.id,
                        element_id=evidence.element_id,
                        document_id=evidence.document_id,
                        quote=evidence.quote,
                    )
                )
            created.append(opportunity)
    session.flush()
    return created
