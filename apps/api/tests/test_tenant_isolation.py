"""The existential tests (docs/05 §1): tenant A's data must be structurally
invisible to tenant B — at the API layer and at the database layer."""

import uuid

from sqlalchemy import select, text

from app.db import get_session_factory, set_org_context
from app.modules.projects.models import Project


def _two_orgs(client, as_user):
    a = as_user("alice@a.example.com", "Alice")
    client.post("/v1/auth/logout")
    b = as_user("bob@b.example.com", "Bob")
    client.post("/v1/auth/logout")
    return a["orgs"][0]["id"], b["orgs"][0]["id"]


def test_api_denies_cross_tenant_access(client, as_user):
    org_a, org_b = _two_orgs(client, as_user)

    as_user("alice@a.example.com")
    project = client.post(f"/v1/orgs/{org_a}/projects", json={"name": "Secret"}).json()
    client.post("/v1/auth/logout")

    as_user("bob@b.example.com")
    # Bob is not a member of org A: existence must not be confirmed (404, not 403).
    assert client.get(f"/v1/orgs/{org_a}/projects").status_code == 404
    assert client.get(f"/v1/orgs/{org_a}/projects/{project['id']}").status_code == 404
    # Bob cannot smuggle A's project id through his own org context either.
    assert client.get(f"/v1/orgs/{org_b}/projects/{project['id']}").status_code == 404


def test_rls_blocks_cross_tenant_reads_even_in_raw_sql(client, as_user):
    org_a, org_b = _two_orgs(client, as_user)
    as_user("alice@a.example.com")
    client.post(f"/v1/orgs/{org_a}/projects", json={"name": "Secret"})

    session = get_session_factory()()
    try:
        # Bound to tenant B: A's rows do not exist.
        set_org_context(session, org_b)
        assert session.execute(select(Project)).scalars().all() == []
        session.rollback()

        # Bound to tenant A: the row is there.
        set_org_context(session, org_a)
        assert len(session.execute(select(Project)).scalars().all()) == 1
        session.rollback()

        # No tenant context at all: RLS fails closed — zero rows.
        assert session.execute(select(Project)).scalars().all() == []
    finally:
        session.close()


def test_rls_blocks_cross_tenant_writes(client, as_user):
    org_a, org_b = _two_orgs(client, as_user)

    session = get_session_factory()()
    try:
        set_org_context(session, org_b)
        session.add(Project(org_id=uuid.UUID(org_a), name="forged"))
        try:
            session.flush()
            inserted = True
        except Exception:
            inserted = False
        session.rollback()
        assert not inserted, "RLS WITH CHECK must reject rows for another org"
    finally:
        session.close()


def test_audit_log_is_append_only(client, as_user):
    me = as_user()
    org_id = me["orgs"][0]["id"]
    client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"})

    session = get_session_factory()()
    try:
        set_org_context(session, org_id)
        try:
            session.execute(text("UPDATE audit_events SET action = 'tampered'"))
            session.commit()
            tampered = True
        except Exception:
            session.rollback()
            tampered = False
        assert not tampered, "audit_events must reject UPDATE"
    finally:
        session.close()
