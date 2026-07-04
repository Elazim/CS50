"""ROI arithmetic: pure functions, exhaustively boring on purpose."""

import pytest

from app.modules.opportunities import roi
from app.modules.opportunities.models import OpportunityTaxonomy


def _set(assumptions, key, value):
    return [
        {**a, "value": value} if a["key"] == key else a for a in assumptions
    ]


def test_compute_known_example():
    assumptions = [
        {"key": "volume_per_month", "value": 1000, "unit": "items", "source": "analyst"},
        {"key": "minutes_per_item", "value": 12, "unit": "minutes", "source": "analyst"},
        {"key": "loaded_hourly_rate", "value": 50, "unit": "USD/hour", "source": "analyst"},
        {"key": "effort_reduction", "value": 0.5, "unit": "ratio", "source": "analyst"},
        {"key": "implementation_cost", "value": 120000, "unit": "USD", "source": "analyst"},
        {"key": "annual_run_cost", "value": 20000, "unit": "USD", "source": "analyst"},
    ]
    computed = roi.compute(assumptions)
    # 1000 * 12mo * 12min * 0.5 / 60 = 1200 hours
    assert computed["annual_hours_saved"] == 1200
    assert computed["gross_annual_savings"] == 60000
    assert computed["net_annual_savings"] == 40000
    # 120000 / (40000/12) = 36 months
    assert computed["payback_months"] == 36.0
    assert computed["three_year_net"] == 0
    assert computed["fte_equivalent"] == round(1200 / 1800, 2)


def test_negative_net_savings_has_no_payback():
    assumptions = roi.propose_assumptions(OpportunityTaxonomy.rpa)
    assumptions = _set(assumptions, "volume_per_month", 1)
    computed = roi.compute(assumptions)
    assert computed["payback_months"] is None
    assert computed["net_annual_savings"] < 0


def test_missing_assumption_is_an_error_not_a_guess():
    with pytest.raises(ValueError, match="missing"):
        roi.compute([{"key": "volume_per_month", "value": 10}])


def test_proposals_are_flagged_estimates_and_computable():
    for taxonomy in OpportunityTaxonomy:
        assumptions = roi.propose_assumptions(taxonomy)
        assert all(a["source"] == "estimate" for a in assumptions), (
            "AI-proposed numbers must be flagged as estimates (docs/01 §2.5)"
        )
        computed = roi.compute(assumptions)
        assert "net_annual_savings" in computed
