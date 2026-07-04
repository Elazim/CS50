"""S3-compatible object storage (MinIO in dev). Keys are always org-prefixed
so tenancy is visible in the storage layout itself (docs/05 §2)."""

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.config import get_settings


@lru_cache
def s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def document_blob_key(
    org_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID, filename: str
) -> str:
    safe_name = filename.replace("/", "_")
    return f"org/{org_id}/projects/{project_id}/documents/{document_id}/{safe_name}"


def presign_put(key: str, mime: str, expires_seconds: int = 900) -> str:
    return s3_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": get_settings().s3_bucket, "Key": key, "ContentType": mime},
        ExpiresIn=expires_seconds,
    )


def head_object(key: str) -> dict | None:
    try:
        return s3_client().head_object(Bucket=get_settings().s3_bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey"):
            return None
        raise


def put_object_bytes(key: str, data: bytes, mime: str) -> None:
    s3_client().put_object(
        Bucket=get_settings().s3_bucket, Key=key, Body=data, ContentType=mime
    )


def get_object_bytes(key: str) -> bytes:
    obj = s3_client().get_object(Bucket=get_settings().s3_bucket, Key=key)
    return obj["Body"].read()


def ensure_bucket() -> None:
    """Dev convenience only; in prod the bucket is provisioned infrastructure."""
    client = s3_client()
    bucket = get_settings().s3_bucket
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)
