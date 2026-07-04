"""M3 integration: generate → review → ROI edit/recompute → roadmap."""

from evals import corpus

from tests.helpers import create_project, ingest_document

CORPUS_FOR_M3 = [
    "claims-intake-sop.md",
    "adjuster-assignment-procedure.docx",
    "subrogation-process.md",
    "ops-weekly-2026-05-12.md",
]


def _corpus_doc(name: str) -> corpus.CorpusDoc:
    return next(d for d in corpus.build_corpus() if d.filename == name)


def _project_with_opportunities(client, as_user):
    org_id, project_id = create_project(client, as_user, "M3")
    for name in CORPUS_FOR_M3:
        ingest_document(client, org_id, project_id, _corpus_doc(name))
    run = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/knowledge/extract")
    assert (
        client.get(
            f"/v1/orgs/{org_id}/pipeline-runs/{run.json()['pipeline_run_id']}"
        ).json()["status"]
        == "succeeded"
    )
    run = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/opportunities/generate")
    assert run.status_code == 202
    status = client.get(
        f"/v1/orgs/{org_id}/pipeline-runs/{run.json()['pipeline_run_id']}"
    ).json()
    assert status["status"] == "succeeded", status
    return org_id, project_id


def test_opportunities_bind_to_pain_points_with_evidence(client, as_user):
    org_id, project_id = _project_with_opportunities(client, as_user)
    opportunities = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()
    assert opportunities, "documented pain points must yield opportunities"
    for opportunity in opportunities:
        assert opportunity["attrs"]["pain_point_ids"], (
            "no free-floating opportunities (docs/06 M3)"
        )
        assert opportunity["evidence"], "opportunities inherit pain-point evidence"
        assert 1 <= opportunity["impact_score"] <= 5
        assert opportunity["rubric_version"] == "1"
        assert opportunity["roi"] is not None
        assert opportunity["roi"]["computed"]["net_annual_savings"] is not None

    # The rekeying pain in the intake SOP must produce an integration play.
    intake_types = {
        o["taxonomy_type"]
        for o in opportunities
        if o["process_name"] and "notice of loss" in o["process_name"].lower()
    }
    assert "system_integration" in intake_types


def test_generation_is_deterministic_across_reruns(client, as_user):
    org_id, project_id = _project_with_opportunities(client, as_user)
    first = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()
    rerun = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities/generate"
    )
    assert (
        client.get(
            f"/v1/orgs/{org_id}/pipeline-runs/{rerun.json()['pipeline_run_id']}"
        ).json()["status"]
        == "succeeded"
    )
    second = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()

    def signature(opportunities):
        return sorted(
            (o["title"], o["impact_score"], o["complexity_score"], o["risk_score"])
            for o in opportunities
        )

    assert signature(first) == signature(second), (
        "same PKM + same rubric version must produce identical scores"
    )


def test_roi_edit_recomputes_in_code(client, as_user):
    org_id, project_id = _project_with_opportunities(client, as_user)
    opportunity = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()[0]

    patched = client.patch(
        f"/v1/orgs/{org_id}/opportunities/{opportunity['id']}/roi",
        json={"assumptions": [
            {"key": "volume_per_month", "value": 2000},
            {"key": "minutes_per_item", "value": 30},
        ]},
    )
    assert patched.status_code == 200, patched.text
    roi = patched.json()
    assert roi["version"] == opportunity["roi"]["version"] + 1
    edited = {a["key"]: a for a in roi["assumptions"]}
    assert edited["volume_per_month"]["source"] == "analyst"
    assert edited["volume_per_month"]["value"] == 2000
    # Untouched assumptions keep their estimate flag.
    assert edited["loaded_hourly_rate"]["source"] == "estimate"
    # And the figures moved with the assumptions — computed, not stored prose.
    assert (
        roi["computed"]["gross_annual_savings"]
        > opportunity["roi"]["computed"]["gross_annual_savings"]
    )

    rejected = client.patch(
        f"/v1/orgs/{org_id}/opportunities/{opportunity['id']}/roi",
        json={"assumptions": [{"key": "volume_per_month", "value": "not-a-number"}]},
    )
    assert rejected.status_code == 400


def test_opportunity_review_flow(client, as_user):
    org_id, project_id = _project_with_opportunities(client, as_user)
    opportunities = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()
    confirmed = client.post(
        f"/v1/orgs/{org_id}/opportunities/{opportunities[0]['id']}/review",
        json={"action": "confirm"},
    ).json()
    assert confirmed["review_state"] == "confirmed"

    client.post(
        f"/v1/orgs/{org_id}/opportunities/{opportunities[1]['id']}/review",
        json={"action": "reject"},
    )
    remaining = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities"
    ).json()
    assert opportunities[1]["id"] not in {o["id"] for o in remaining}

    # Re-generation preserves both judgments.
    rerun = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities/generate"
    )
    client.get(f"/v1/orgs/{org_id}/pipeline-runs/{rerun.json()['pipeline_run_id']}")
    after = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/opportunities?include_rejected=true"
    ).json()
    states = {o["id"]: o["review_state"] for o in after}
    assert states.get(opportunities[0]["id"]) == "confirmed"
    assert states.get(opportunities[1]["id"]) == "rejected"


def test_roadmap_respects_rules_and_dependencies(client, as_user):
    org_id, project_id = _project_with_opportunities(client, as_user)
    roadmap = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/roadmap/generate"
    ).json()

    all_items = [item for items in roadmap["horizons"].values() for item in items]
    assert all_items, "roadmap must sequence the opportunities"

    by_opportunity = {item["opportunity_id"]: item for item in all_items}
    horizon_rank = {"30": 0, "90": 1, "180": 2, "365": 3}
    for item in all_items:
        # Quick-win rule is a rule: impact>=3 and complexity<=2.
        opp = item["opportunity"]
        assert item["quick_win"] == (
            opp["impact_score"] >= 3 and opp["complexity_score"] <= 2
        )
        # A dependent item never lands in an earlier-or-equal horizon than
        # its prerequisite.
        for dependency_id in item["depends_on"]:
            prerequisite = by_opportunity[dependency_id]
            assert (
                horizon_rank[item["horizon"]] > horizon_rank[prerequisite["horizon"]]
            ), "automation must not precede its prerequisite integration"

    # GET returns the same roadmap (persisted, not recomputed per request).
    fetched = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/roadmap").json()
    assert {
        i["id"] for items in fetched["horizons"].values() for i in items
    } == {i["id"] for i in all_items}


def test_roadmap_requires_opportunities(client, as_user):
    org_id, project_id = create_project(client, as_user, "Empty")
    res = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/roadmap/generate")
    assert res.status_code == 400