"""ROI model: assumption templates + pure arithmetic (docs/01 §2.5).

`compute()` is a pure function of the assumption list. Nothing here calls
an LLM; nothing here invents a number. Proposed defaults are explicitly
`source: "estimate"` until an analyst touches them (→ `analyst`) or a
future metric-extraction pass cites them (→ evidence id).
"""

from typing import Any

from app.modules.opportunities.models import OpportunityTaxonomy as T

WORKING_HOURS_PER_YEAR = 1800


def _assumption(key: str, label: str, value: float, unit: str) -> dict:
    return {"key": key, "label": label, "value": value, "unit": unit, "source": "estimate"}


_COMMON = [
    ("volume_per_month", "Affected items per month", 800, "items"),
    ("minutes_per_item", "Minutes of manual effort per item", 12, "minutes"),
    ("loaded_hourly_rate", "Loaded hourly rate of affected staff", 45, "USD/hour"),
]

# Per-type deltas: automation coverage and implementation cost profiles.
_TYPE_PROFILE: dict[T, tuple[float, float]] = {
    # (share of effort removed, implementation cost USD)
    T.rpa: (0.6, 40_000),
    T.workflow_automation: (0.55, 80_000),
    T.system_integration: (0.8, 120_000),
    T.document_ai: (0.5, 90_000),
    T.decision_engine: (0.65, 150_000),
    T.generative_ai: (0.4, 100_000),
    T.knowledge_search: (0.3, 60_000),
    T.process_redesign: (0.35, 50_000),
    T.elimination: (0.9, 10_000),
}


def propose_assumptions(taxonomy: T) -> list[dict]:
    coverage, cost = _TYPE_PROFILE[taxonomy]
    return [
        *[_assumption(*row) for row in _COMMON],
        _assumption("effort_reduction", "Share of effort removed", coverage, "ratio"),
        _assumption("implementation_cost", "Implementation cost", cost, "USD"),
        _assumption("annual_run_cost", "Annual run/licence cost", cost * 0.15, "USD"),
    ]


def compute(assumptions: list[dict]) -> dict[str, Any]:
    values = {a["key"]: float(a["value"]) for a in assumptions}
    required = {
        "volume_per_month", "minutes_per_item", "loaded_hourly_rate",
        "effort_reduction", "implementation_cost", "annual_run_cost",
    }
    missing = required - values.keys()
    if missing:
        raise ValueError(f"ROI assumptions missing: {sorted(missing)}")

    annual_hours_saved = (
        values["volume_per_month"] * 12 * values["minutes_per_item"]
        * values["effort_reduction"] / 60
    )
    gross_annual_savings = annual_hours_saved * values["loaded_hourly_rate"]
    net_annual_savings = gross_annual_savings - values["annual_run_cost"]
    payback_months = (
        values["implementation_cost"] / (net_annual_savings / 12)
        if net_annual_savings > 0
        else None
    )
    three_year_net = net_annual_savings * 3 - values["implementation_cost"]
    fte_equivalent = annual_hours_saved / WORKING_HOURS_PER_YEAR

    return {
        "annual_hours_saved": round(annual_hours_saved),
        "fte_equivalent": round(fte_equivalent, 2),
        "gross_annual_savings": round(gross_annual_savings),
        "net_annual_savings": round(net_annual_savings),
        "payback_months": round(payback_months, 1) if payback_months else None,
        "three_year_net": round(three_year_net),
    }
