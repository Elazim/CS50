"""M1 eval scaffold (docs/03 §7): golden-corpus quality bars enforced in CI.

These are regression tripwires, not vanity metrics: retrieval hit-rate,
classification accuracy, and PII recall over the synthetic corpus. Bars are
calibrated for the deterministic local providers; real-provider runs should
clear them with margin.
"""

from evals import corpus, golden

from tests.helpers import create_project, ingest_document


def _ingest_all(client, as_user):
    org_id, project_id = create_project(client, as_user, "Golden Corpus")
    by_name = {}
    for doc in corpus.build_corpus():
        by_name[doc.filename] = ingest_document(client, org_id, project_id, doc)
    return org_id, project_id, by_name


def test_corpus_ingests_cleanly(client, as_user):
    _, _, by_name = _ingest_all(client, as_user)
    failed = [n for n, d in by_name.items() if d["status"] != "ready"]
    assert not failed, f"corpus documents failed ingestion: {failed}"


def test_retrieval_hit_rate_bar(client, as_user):
    org_id, project_id, _ = _ingest_all(client, as_user)
    hits = 0
    misses = []
    for case in golden.RETRIEVAL_CASES:
        results = client.post(
            f"/v1/orgs/{org_id}/projects/{project_id}/search",
            json={"query": case.query, "top_k": case.within_top},
        ).json()
        found = any(
            r["filename"] == case.expected_filename
            or any(accept.lower() in r["text"].lower() for accept in case.accept_text)
            for r in results
        )
        if found:
            hits += 1
        else:
            misses.append(case.query)
    rate = hits / len(golden.RETRIEVAL_CASES)
    assert rate >= golden.RETRIEVAL_HIT_RATE_BAR, (
        f"retrieval hit-rate {rate:.2f} below bar "
        f"{golden.RETRIEVAL_HIT_RATE_BAR}; misses: {misses}"
    )


def test_classification_accuracy_bar(client, as_user):
    org_id, _, by_name = _ingest_all(client, as_user)
    correct = 0
    wrong = {}
    for filename, expected in golden.CLASSIFICATION_EXPECTED.items():
        detail = client.get(f"/v1/orgs/{org_id}/documents/{by_name[filename]['id']}").json()
        if detail["doc_class"] == expected:
            correct += 1
        else:
            wrong[filename] = (expected, detail["doc_class"])
    accuracy = correct / len(golden.CLASSIFICATION_EXPECTED)
    assert accuracy >= golden.CLASSIFICATION_ACCURACY_BAR, (
        f"classification accuracy {accuracy:.2f} below bar; wrong: {wrong}"
    )


def test_extraction_bars_over_full_corpus(client, as_user):
    org_id, project_id, _ = _ingest_all(client, as_user)
    res = client.post(f"/v1/orgs/{org_id}/projects/{project_id}/knowledge/extract")
    run = client.get(
        f"/v1/orgs/{org_id}/pipeline-runs/{res.json()['pipeline_run_id']}"
    ).json()
    assert run["status"] == "succeeded", run

    entities = client.get(
        f"/v1/orgs/{org_id}/projects/{project_id}/entities?limit=500"
    ).json()
    by_type: dict[str, list] = {}
    for entity in entities:
        by_type.setdefault(entity["type"], []).append(entity)

    actor_names = {e["name"] for e in by_type.get("actor", [])}
    found = [a for a in golden.EXTRACTION_EXPECTED_ACTORS if a in actor_names]
    recall = len(found) / len(golden.EXTRACTION_EXPECTED_ACTORS)
    assert recall >= golden.ACTOR_RECALL_BAR, (
        f"actor recall {recall:.2f} below bar; "
        f"missing: {set(golden.EXTRACTION_EXPECTED_ACTORS) - actor_names}"
    )

    system_names = {e["name"] for e in by_type.get("system", [])}
    assert set(golden.EXTRACTION_EXPECTED_SYSTEMS) <= system_names

    taxonomies = {
        e["attrs"].get("taxonomy") for e in by_type.get("pain_point", [])
    }
    assert taxonomies >= golden.EXTRACTION_EXPECTED_TAXONOMIES, (
        f"missing waste taxonomies: {golden.EXTRACTION_EXPECTED_TAXONOMIES - taxonomies}"
    )

    processes = by_type.get("process", [])
    assert len(processes) >= golden.MIN_PROCESSES
    intake = next((p for p in processes if "notice of loss" in p["name"].lower()), None)
    assert intake is not None, "the FNOL intake process must be identified"
    graph = client.get(f"/v1/orgs/{org_id}/processes/{intake['id']}/graph").json()
    assert len(graph["nodes"]) >= golden.MIN_STEPS_PER_MAIN_PROCESS

    assert all(e["evidence"] for e in entities), "evidence coverage must be 100%"


def test_pii_recall_on_planted_identifiers(client, as_user):
    org_id, _, by_name = _ingest_all(client, as_user)
    doc = by_name["customer-complaints-log.xlsx"]
    detail = client.get(f"/v1/orgs/{org_id}/documents/{doc['id']}").json()
    counts = detail["pii_summary"]["counts"]
    for pii_type, minimum in golden.PII_EXPECTED_MIN.items():
        assert counts.get(pii_type, 0) >= minimum, (
            f"expected ≥{minimum} {pii_type}, found {counts.get(pii_type, 0)}"
        )
