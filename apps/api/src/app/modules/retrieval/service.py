"""Hybrid retrieval (docs/03 §2): vector KNN + lexical full-text, fused
with reciprocal-rank fusion. One database, one query path, provenance
(element ids, pages, section path) on every hit — results are citable,
never bare text.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.providers import get_embedding_provider
from app.modules.documents.elements import Chunk
from app.modules.documents.models import Document

RRF_K = 60
CANDIDATES_PER_ARM = 30


@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    doc_class: str | None
    text: str
    score: float
    section_path: list
    pages: list
    element_ids: list[uuid.UUID]


def search_chunks(
    session: Session,
    *,
    project_id: uuid.UUID,
    query: str,
    top_k: int = 8,
) -> list[SearchResult]:
    ranked: dict[uuid.UUID, float] = {}

    # Arm 1: vector KNN (cosine distance)
    query_embedding = get_embedding_provider().embed([query], input_type="query")[0]
    vector_rows = session.execute(
        select(Chunk.id)
        .where(Chunk.project_id == project_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(CANDIDATES_PER_ARM)
    ).all()
    for rank, (chunk_id,) in enumerate(vector_rows):
        ranked[chunk_id] = ranked.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    # Arm 2: lexical full-text (websearch syntax: quoted phrases, -exclusions)
    tsquery = func.websearch_to_tsquery("english", query)
    lexical_rows = session.execute(
        select(Chunk.id)
        .where(Chunk.project_id == project_id, Chunk.tsv.op("@@")(tsquery))
        .order_by(func.ts_rank(Chunk.tsv, tsquery).desc())
        .limit(CANDIDATES_PER_ARM)
    ).all()
    for rank, (chunk_id,) in enumerate(lexical_rows):
        ranked[chunk_id] = ranked.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

    if not ranked:
        return []

    top_ids = sorted(ranked, key=lambda cid: ranked[cid], reverse=True)[:top_k]
    rows = session.execute(
        select(Chunk, Document.filename, Document.doc_class)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_(top_ids))
    ).all()
    by_id = {chunk.id: (chunk, filename, doc_class) for chunk, filename, doc_class in rows}

    results = []
    for chunk_id in top_ids:
        chunk, filename, doc_class = by_id[chunk_id]
        meta = chunk.meta or {}
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                doc_class=doc_class,
                text=chunk.text,
                score=round(ranked[chunk_id], 6),
                section_path=meta.get("section_path", []),
                pages=meta.get("pages", []),
                element_ids=list(chunk.element_ids or []),
            )
        )
    return results
