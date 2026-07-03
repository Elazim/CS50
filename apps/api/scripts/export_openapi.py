"""Dump the OpenAPI schema to stdout (CI regenerates the TS client from it)."""

import json
import os

os.environ.setdefault("ATC_ENV", "test")
os.environ.setdefault("ATC_DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")

from app.main import app  # noqa: E402

print(json.dumps(app.openapi(), indent=2, sort_keys=True))  # noqa: T201
