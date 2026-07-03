def test_dev_login_bootstraps_workspace(client, as_user):
    me = as_user("first@example.com", "First User")
    assert me["email"] == "first@example.com"
    assert len(me["orgs"]) == 1
    assert me["orgs"][0]["role"] == "org_admin"
    assert "Workspace" in me["orgs"][0]["name"]


def test_me_requires_session(client):
    res = client.get("/v1/auth/me")
    assert res.status_code == 401


def test_logout_clears_session(client, as_user):
    as_user()
    assert client.get("/v1/auth/me").status_code == 200
    client.post("/v1/auth/logout")
    assert client.get("/v1/auth/me").status_code == 401


def test_dev_login_is_idempotent(client, as_user):
    first = as_user("same@example.com")
    second = as_user("same@example.com")
    assert first["id"] == second["id"]
    assert len(second["orgs"]) == 1  # no duplicate workspace
