"""End-to-end M1 slice: upload through the API → full ingest pipeline →
elements, chunks, classification, PII tags → hybrid search with citations."""

from evals import corpus
from sqlalchemy import select

from app.db import get_session_factory, set_org_context
from app.modules.documents.elements import Chunk, UsageEvent
from tests.helpers import create_project, ingest_document


def _corpus_doc(name: str) -> corpus.CorpusDoc:
    return next(d for d in corpus.build_corpus() if d.filename == name)


def test_ingest_produces_elements_chunks_and_class(client, as_user):
    org_id, project_id = create_project(client, as_user)
    doc = ingest_document(client, org_id, project_id, _corpus_doc("claims-intake-sop.md"))
    assert doc["status"] == "ready"

    detail = client.get(f"/v1/orgs/{org_id}/documents/{doc['id']}").json()
    assert detail["doc_class"] == "sop"
    assert detail["element_count"] > 10
    kinds = {e["kind"] for e in detail["elements"]}
    assert {"heading", "paragraph", "list_item"} <= kinds

    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        chunks = session.execute(select(Chunk)).scalars().all()
        assert chunks, "ingest must produce chunks"
        assert all(c.embedding is not None for c in chunks)
        assert all(c.element_ids for c in chunks)
        usage = session.execute(select(UsageEvent)).scalars().all()
        assert any(u.kind == "embedding" and u.tokens_in > 0 for u in usage)
    finally:
        session.close()


def test_pii_tagging_flows_to_api(client, as_user):
    org_id, project_id = create_project(client, as_user)
    doc = ingest_document(
        client, org_id, project_id, _corpus_doc("customer-complaints-log.xlsx")
    )
    detail = client.get(f"/v1/orgs/{org_id}/documents/{doc['id']}").json()
    counts = detail["pii_summary"]["counts"]
    assert counts["email"] >= 4
    assert counts["policy_number"] >= 4
    table_element = detail["elements"][0]
    assert "email" in table_element["pii_types"]


def test_search_returns_cited_hits(client, as_user):
    org_id, project_id = create_project(client, as_user)
    for name in ("claims-intake-sop.md", "claims-triage-policy.md"):
        ingest_document(client, org_id, project_id, _corpus_doc(name))

    res = client.post(
        f"/v1/orgs/{org_id}/projects/{project_id}/search",
        json={"query": "severity tiers for triage", "top_k": 5},
    )
    assert res.status_code == 200, res.text
    hits = res.json()
    assert hits, "hybrid search must return results"
    top = hits[0]
    assert top["filename"] == "claims-triage-policy.md"
    assert top["element_ids"], "every hit must carry element provenance"
    assert top["score"] > 0

    # Provenance is dereferenceable: cited elements exist in the document view.
    detail = client.get(f"/v1/orgs/{org_id}/documents/{top['document_id']}").json()
    element_ids = {e["id"] for e in detail["elements"]}
    assert set(top["element_ids"]) <= element_ids


def test_search_is_project_scoped(client, as_user):
    org_id, project_a = create_project(client, as_user, "A")
    project_b = client.post(f"/v1/orgs/{org_id}/projects", json={"name": "B"}).json()["id"]
    ingest_document(client, org_id, project_a, _corpus_doc("claims-glossary.txt"))

    hits = client.post(
        f"/v1/orgs/{org_id}/projects/{project_b}/search",
        json={"query": "what does FNOL mean"},
    ).json()
    assert hits == []


def test_failed_parse_marks_document_failed(client, as_user):
    org_id, project_id = create_project(client, as_user)
    bad = corpus.CorpusDoc("scan.pdf", "application/pdf", b"%PDF-1.4 not really a pdf")
    doc = ingest_document(client, org_id, project_id, bad)
    assert doc["status"] in ("failed", "processing")
    listed = client.get(f"/v1/orgs/{org_id}/projects/{project_id}/documents").json()
    assert listed[0]["status"] == "failed"
    assert listed[0]["latest_run_status"] == "failed"
