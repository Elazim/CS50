def test_project_crud_and_audit(client, as_user):
    me = as_user()
    org_id = me["orgs"][0]["id"]

    created = client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "Claims Intake Assessment"}
    )
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["industry_pack"] == "insurance-claims"

    listed = client.get(f"/v1/orgs/{org_id}/projects").json()
    assert [p["id"] for p in listed] == [project["id"]]

    fetched = client.get(f"/v1/orgs/{org_id}/projects/{project['id']}")
    assert fetched.status_code == 200


def test_unknown_project_is_404(client, as_user):
    me = as_user()
    org_id = me["orgs"][0]["id"]
    res = client.get(f"/v1/orgs/{org_id}/projects/00000000-0000-0000-0000-000000000000")
    assert res.status_code == 404
