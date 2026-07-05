"""Test harness: real Postgres (RLS on), in-memory S3 (moto), eager Celery.

Environment is pinned before any `app` import so the settings cache and the
FastAPI app pick up test configuration.
"""

import os

os.environ.setdefault(
    "ATC_DATABASE_URL", "postgresql+psycopg://atc:atc@127.0.0.1:54329/atc_test"
)
os.environ["ATC_ENV"] = "test"
os.environ["ATC_CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["ATC_S3_ENDPOINT_URL"] = ""  # real-AWS shape so moto can intercept
os.environ["ATC_S3_BUCKET"] = "atc-test-documents"

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import text

from app import storage
from app.config import get_settings
from app.db import get_engine
from app.main import app

TENANT_AND_ACCOUNT_TABLES = [
    "audit_events",
    "pipeline_steps",
    "pipeline_runs",
    "documents",
    "projects",
    "memberships",
    "users",
    "orgs",
]


@pytest.fixture(scope="session", autouse=True)
def database():
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(database):
    yield
    with get_engine().begin() as conn:
        # TRUNCATE is not governed by RLS; table owner may clear everything.
        conn.execute(text(f"TRUNCATE {', '.join(TENANT_AND_ACCOUNT_TABLES)} CASCADE"))


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    from app.middleware import reset_rate_limits

    reset_rate_limits()
    yield


@pytest.fixture(autouse=True)
def object_storage():
    with mock_aws():
        storage.s3_client.cache_clear()
        storage.s3_client().create_bucket(Bucket=get_settings().s3_bucket)
        yield
    storage.s3_client.cache_clear()


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def as_user(client):
    """Sign in a dev user; returns the client (cookie jar now authenticated)."""

    def _login(email: str = "ana@example.com", name: str = "Ana Analyst"):
        res = client.post("/v1/auth/dev-login", json={"email": email, "name": name})
        assert res.status_code == 200, res.text
        return res.json()

    return _login
