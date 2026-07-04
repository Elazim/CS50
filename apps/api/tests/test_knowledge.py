"""M2 integration: extraction → review loop → merge → graph → BPMN."""

import uuid
from xml.etree import ElementTree as ET

import pytest
from evals import corpus

from app.db import get_session_factory, set_org_context
from app.modules.knowledge.models import Confidence
from app.modules.knowledge.service import EvidenceInvariantError, ExtractedItem, create_entity
from tests.helpers import create_project, ingest_document

BPMN_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"


def _corpus_doc(name: str) -> corpus.CorpusDoc:
    return next(d for d in corpus.build_corpus() if d.filename == name)


def _extracted_project(client, as_user, filenames: list[str]):
    org_id, project_id = create_project(client, as_user, "Knowledge")
    for name in filenames:
        ingest_document(client, org_id, project_id, _corpus_doc(name))
    res = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/knowledge/extract")
    assert res.status_code == 202, res.text
    run_id = res.json()["pipeline_run_id"]
    run = client.get(f"/v1/orgs/{org_id}/pipeline-runs/{run_id}").json()
    assert run["status"] == "succeeded", run
    return org_id, project_id


def test_extraction_builds_knowledge_model(client, as_user):
    org_id, project_id = _extracted_project(
        client, as_user, ["claims-intake-sop.md", "ops-weekly-2026-05-12.md"]
    )
    entities = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/entities").json()
    by_type: dict[str, list] = {}
    for entity in entities:
        by_type.setdefault(entity["type"], []).append(entity)

    actor_names = {e["name"] for e in by_type.get("actor", [])}
    assert "Intake Coordinator" in actor_names
    system_names = {e["name"] for e in by_type.get("system", [])}
    assert {"ClaimCore", "CallTrak", "PolicyHub"} <= system_names
    assert by_type.get("process"), "the intake SOP must yield a process"
    assert by_type.get("process_step"), "the SOP's registration steps must yield steps"
    pains = by_type.get("pain_point", [])
    assert any(p["attrs"].get("taxonomy") == "rework" for p in pains), (
        "rekeying between CallTrak and ClaimCore must surface as rework"
    )
    # The evidence invariant, observed from the outside: every entity cites.
    assert all(e["evidence"] for e in entities), "every assertion must carry evidence"


def test_low_confidence_items_enter_review_queue(client, as_user):
    org_id, project_id = _extracted_project(client, as_user, ["claims-intake-sop.md"])
    items = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/review-items").json()
    assert items, "medium/low-confidence extractions must queue questions"
    assert any(i["kind"] == "low_confidence" for i in items)
    # Queue items carry their subject entity with evidence for the panel.
    with_subject = [i for i in items if i["subject"]]
    assert with_subject and with_subject[0]["subject"]["evidence"]


def test_review_confirm_reject_edit_with_history(client, as_user):
    org_id, project_id = _extracted_project(client, as_user, ["claims-intake-sop.md"])
    entities = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?type=pain_point"
    ).json()
    target = entities[0]

    confirmed = client.post(
        f"/v1/orgs/{org_id}/entities/{target['id']}/review", json={"action": "confirm"}
    ).json()
    assert confirmed["review_state"] == "confirmed"
    assert confirmed["version"] == target["version"] + 1

    edited = client.post(
        f"/v1/orgs/{org_id}/entities/{entities[1]['id']}/review",
        json={"action": "edit", "edits": {"name": "Manual rekeying at intake"}},
    ).json()
    assert edited["review_state"] == "edited"
    assert edited["name"] == "Manual rekeying at intake"

    # Confirming resolves the entity's open low-confidence question.
    items = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/review-items").json()
    open_subjects = {i["subject_id"] for i in items}
    assert target["id"] not in open_subjects


def test_merge_proposal_resolution_merges_entities(client, as_user):
    org_id, project_id = _extracted_project(
        client, as_user, ["claims-intake-sop.md", "adjuster-assignment-procedure.docx"]
    )
    items = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/review-items").json()
    proposals = [i for i in items if i["kind"] == "merge_proposal"]
    assert proposals, "similar actor names must produce merge proposals"

    proposal = proposals[0]
    resolved = client.post(
        f"/v1/orgs/{org_id}/review-items/{proposal['id']}/resolve",
        json={"action": "merge"},
    ).json()
    assert resolved["status"] == "resolved"

    kept = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?include_rejected=true"
    ).json()
    merged_away = [
        e for e in kept if e["attrs"].get("merged_into") == proposal["subject_id"]
    ]
    assert merged_away and merged_away[0]["review_state"] == "rejected"
    keeper = next(e for e in kept if e["id"] == proposal["subject_id"])
    assert merged_away[0]["name"] in keeper["attrs"]["aliases"]


def test_process_graph_and_bpmn_export(client, as_user):
    org_id, project_id = _extracted_project(client, as_user, ["claims-intake-sop.md"])
    processes = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?type=process"
    ).json()
    process_id = processes[0]["id"]

    graph = client.get(f"/v1/orgs/{org_id}/processes/{process_id}/graph").json()
    assert len(graph["nodes"]) >= 4, "intake SOP has 5 registration steps"
    assert graph["edges"], "sequential steps must be linked by precedes edges"
    orders = [n["order"] for n in graph["nodes"]]
    assert orders == sorted(orders)
    assert any(n["step_type"] == "manual" for n in graph["nodes"])
    assert all(n["evidence"] for n in graph["nodes"])

    bpmn = client.get(f"/v1/orgs/{org_id}/processes/{process_id}/bpmn")
    assert bpmn.status_code == 200
    root = ET.fromstring(bpmn.text)  # must be valid XML
    process_el = root.find(f"{BPMN_NS}process")
    assert process_el is not None
    tasks = [el for el in process_el.iter() if el.tag.endswith("Task") or el.tag.endswith("}task")]
    flows = process_el.findall(f"{BPMN_NS}sequenceFlow")
    assert len(tasks) + len(flows) >= len(graph["nodes"])
    assert root.find(
        "{http://www.omg.org/spec/BPMN/20100524/DI}BPMNDiagram"
    ) is not None, "diagram interchange (layout) must be present"


def test_reextraction_preserves_analyst_work(client, as_user):
    org_id, project_id = _extracted_project(client, as_user, ["claims-intake-sop.md"])
    entities = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?type=pain_point"
    ).json()
    confirmed_id = entities[0]["id"]
    client.post(f"/v1/orgs/{org_id}/entities/{confirmed_id}/review", json={"action": "confirm"})

    res = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/knowledge/extract")
    run = client.get(
        f"/v1/orgs/{org_id}/pipeline-runs/{res.json()['pipeline_run_id']}"
    ).json()
    assert run["status"] == "succeeded"

    after = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?type=pain_point"
    ).json()
    survivors = {e["id"] for e in after}
    assert confirmed_id in survivors, "re-extraction must never clobber confirmed work"


def test_evidence_invariant_enforced_in_write_path(client, as_user):
    org_id, project_id = create_project(client, as_user, "Invariant")
    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        with pytest.raises(EvidenceInvariantError):
            create_entity(
                session,
                org_id=uuid.UUID(org_id),
                project_id=uuid.UUID(project_id),
                item=ExtractedItem("actor", "Ghost Actor", Confidence.high, evidence=[]),
            )
        session.rollback()
    finally:
        session.close()
