"""Versioned scoring rubric (docs/03 §5).

Deterministic: the same knowledge model and rubric version always produce
the same scores — scores are explainable rules, not vibes. Changing a rule
means bumping RUBRIC_VERSION so historical scores stay interpretable.

Scales are 1–5: impact (5 = large, recurring value), complexity
(5 = hardest to implement), risk (5 = riskiest).
"""

from app.modules.opportunities.models import OpportunityTaxonomy as T

RUBRIC_VERSION = "1"

# Waste taxonomy (pain cues, docs/03 §3) → candidate opportunity types,
# in preference order. The generator picks per pain-point cluster.
TAXONOMY_TO_OPPORTUNITY: dict[str, list[T]] = {
    "rework": [T.system_integration, T.rpa],
    "manual_work": [T.workflow_automation, T.document_ai],
    "waiting": [T.decision_engine, T.workflow_automation],
    "handoff_friction": [T.workflow_automation, T.process_redesign],
    "defects": [T.workflow_automation, T.decision_engine],
    "shadow_it": [T.system_integration, T.process_redesign],
}

# Base complexity/risk per opportunity type — implementation reality, not
# enthusiasm. (RPA is quick and brittle; integrations are slower and sturdy.)
BASE_COMPLEXITY: dict[T, int] = {
    T.rpa: 2,
    T.workflow_automation: 3,
    T.system_integration: 3,
    T.document_ai: 3,
    T.knowledge_search: 2,
    T.generative_ai: 3,
    T.decision_engine: 4,
    T.process_redesign: 4,
    T.elimination: 1,
}
BASE_RISK: dict[T, int] = {
    T.rpa: 3,          # brittle to UI change
    T.workflow_automation: 2,
    T.system_integration: 2,
    T.document_ai: 3,
    T.knowledge_search: 2,
    T.generative_ai: 4,  # output-quality risk in regulated ops
    T.decision_engine: 4,  # decisioning in insurance draws regulatory scrutiny
    T.process_redesign: 3,
    T.elimination: 2,
}


def score_impact(pain_point_count: int, distinct_taxonomies: int, step_count: int) -> int:
    """More distinct evidence of waste on a bigger process → more impact."""
    score = 1
    score += min(pain_point_count, 3)          # up to +3
    if distinct_taxonomies >= 2:
        score += 1
    if step_count >= 5:
        score += 1
    return min(score, 5)


def score_complexity(taxonomy: T, systems_involved: int) -> int:
    score = BASE_COMPLEXITY[taxonomy]
    if systems_involved >= 2:
        score += 1
    return min(score, 5)


def score_risk(taxonomy: T, has_compliance_context: bool) -> int:
    score = BASE_RISK[taxonomy]
    if has_compliance_context:
        score += 1
    return min(score, 5)


def is_quick_win(impact: int, complexity: int) -> bool:
    """The quick-win rule is a rule, not a vibe (docs/03 §5)."""
    return impact >= 3 and complexity <= 2


def horizon_for(impact: int, complexity: int, risk: int) -> str:
    if is_quick_win(impact, complexity):
        return "30"
    if complexity <= 3 and risk <= 3:
        return "90"
    if complexity <= 4:
        return "180"
    return "365"
