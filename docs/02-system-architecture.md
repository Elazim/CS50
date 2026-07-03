# 02 — System Architecture

Every choice below is stated as **Decision / Alternatives considered / Why**, because you asked for justified tradeoffs. The governing constraints: one primary engineer (AI-assisted), enterprise buyers eventually doing security review, document/AI pipelines as the computational core, and a stack that must not require a platform team to operate.

---

## 1. Shape of the system

**Decision: a modular monolith split by runtime, not by domain — three deployables, one database.**

```
┌─────────────┐   HTTPS    ┌──────────────────┐    jobs     ┌──────────────────┐
│  apps/web    │ ─────────► │  apps/api         │ ──────────► │  apps/worker      │
│  Next.js     │  OpenAPI-  │  FastAPI (Python) │   Redis     │  Python pipeline  │
│  (Vercel/    │  generated │  REST + SSE       │   queue     │  (ingest/extract/ │
│   container) │  TS client │                   │ ◄────────── │   generate)       │
└─────────────┘            └────────┬─────────┘   progress   └────────┬─────────┘
                                     │                                  │
                          ┌──────────▼──────────────────────────────────▼──────┐
                          │ PostgreSQL 16 (+ pgvector)   │  S3-compatible blob │
                          │ single source of truth       │  storage (files)    │
                          └─────────────────────────────────────────────────────┘
```

- **apps/web** — Next.js UI. Talks only to the API via a generated typed client.
- **apps/api** — FastAPI. Owns authZ, tenancy enforcement, CRUD, job dispatch, exports, SSE progress streams.
- **apps/worker** — same Python codebase, different entrypoint. Runs the long-running pipelines (parsing, OCR, extraction, embedding, deliverable generation). Scales independently because pipeline load is bursty (a 300-document upload) while API load is steady.

**Alternatives considered:**
- *Microservices per module* — rejected. Ten services for one engineer is an operations hobby, not a product. Domain modularity lives in the code layout (`modules/documents`, `modules/processes`, `modules/opportunities`…), each module owning its models/services/routes, so a future extraction into a service is a refactor, not a rewrite.
- *Single Next.js full-stack app (API routes + TS workers)* — genuinely attractive (one language, shared types), and the default answer for most SaaS. Rejected here because **the computational core is document processing and LLM orchestration, where Python's ecosystem is a step-function ahead**: `unstructured`/`PyMuPDF`/`python-docx`/`openpyxl`/`python-pptx` for parsing, mature OCR bindings, `pydantic` for extraction schemas, `python-pptx`/`docxtpl` for the export engine. Fighting the ecosystem in TS costs more than maintaining two languages.
- The type-safety loss at the TS/Python boundary is mitigated mechanically: FastAPI emits OpenAPI → `openapi-typescript` generates the client in CI → a schema drift is a build failure, not a runtime bug.

## 2. Frontend

**Decision: Next.js 15 (App Router) + TypeScript strict + Tailwind CSS + shadcn/ui + TanStack Query.**

- **Why Next.js:** the app is a document-heavy workspace (Linear/Notion-class UI) that also needs fast marketing/docs pages; one framework covers both. Server components keep the document-list/report views light; client components carry the interactive canvases. Largest hiring pool and AI-codegen corpus — velocity matters more than novelty.
- **Why shadcn/ui + Tailwind:** owns-the-code component model (no design-system lock-in), dark-mode-first tokens, and it visually matches the Linear/Vercel aesthetic target out of the box. Alternatives (MUI, Ant) read "internal tool," which contradicts the brand.
- **Diagramming:** `bpmn-js` for BPMN 2.0 render/edit (the standard, battle-tested, and BPMN XML becomes an *export format* for interop with Visio/Camunda/Signavio); **React Flow** for the opportunity maps and knowledge-graph views where BPMN semantics don't apply. Diagrams are **data (JSON/BPMN-XML) rendered client-side**, never LLM-generated images — they must be editable and re-exportable.
- **State:** TanStack Query for server state (plus SSE subscriptions for pipeline progress); Zustand only where genuine client-local state exists (canvas UI state). No Redux — ceremony without payoff at this scale.

## 3. Backend & jobs

**Decision: FastAPI + Pydantic v2 + SQLAlchemy 2.0/Alembic; Celery on Redis for background jobs.**

- **FastAPI:** async-native (LLM calls are I/O-bound), Pydantic request/response models double as the extraction-schema layer (docs/03 §3), automatic OpenAPI for the client-generation pipeline above.
- **Celery + Redis:** the boring, proven choice. *Alternatives:* **Temporal** — the technically superior answer for durable multi-step workflows, rejected for now because self-hosting it (or paying for Cloud) plus learning its programming model is real cost before revenue. The mitigation making Celery safe: **every pipeline step is idempotent and checkpointed in Postgres** (`pipeline_runs` / `pipeline_steps` tables, docs/04) so a crashed worker resumes from the last completed step instead of relying on broker semantics. **Migration trigger to Temporal:** when pipelines exceed ~30 min of wall-clock with human-in-the-loop pauses inside the workflow, or when retry choreography starts being hand-rolled.
- **SSE over WebSockets** for progress/streaming: unidirectional server→client covers every current need (pipeline progress, generation streaming), survives proxies better, and is far less stateful to operate. WebSockets only if/when real-time co-editing arrives (deferred).

## 4. Data layer

**Decision: PostgreSQL 16 as the single source of truth — relational core, `JSONB` for extraction payloads, `pgvector` for embeddings, `tsvector` for lexical search. S3-compatible object storage (MinIO in dev, S3/R2 in prod) for original files and rendered exports.**

- **Why one database:** the killer feature of the knowledge model is **joinability** — "pain points WHERE process = claims-intake AND evidence.confidence > x, JOIN opportunities" is a SQL query when everything lives together, and a distributed-systems project when it doesn't. Row-Level Security gives structural tenant isolation (docs/05 §2).
- **Why not a dedicated vector DB (Pinecone/Weaviate/Qdrant):** at v1 scale (thousands of documents/tenant, ~10⁵–10⁶ chunks) pgvector with HNSW is comfortably sufficient, keeps vectors transactionally consistent with their source rows, and eliminates a whole class of sync bugs plus a vendor. **Migration trigger:** sustained corpora >10–20M chunks or p95 retrieval latency degrading under filtered search — and the `retrieval` module is the only code that would change.
- **Why not Neo4j for the knowledge graph:** the "graph" is entities + typed relations, which Postgres models fine (`entities`, `entity_relations` tables) at the traversal depths we need (1–3 hops). A graph database is justified by deep traversal/centrality analytics — a later capability, and an *additional* index over the same truth, not a replacement store.

## 5. Authentication & authorization

**Decision: WorkOS for authN (email/password + Google OAuth now; SSO/SAML + SCIM later on the same integration); authZ in-app as RBAC enforced at the API layer + Postgres RLS.**

- *Alternatives:* **Auth0** (comparable, pricier at enterprise tiers), **Keycloak** (free, but self-hosting an identity server as a solo operator is undiluted risk), **roll-your-own + `better-auth`** (fine until the first enterprise asks for SAML, then a rewrite under sales pressure). WorkOS is purpose-built for exactly this trajectory: cheap at seed, enterprise SSO is a config change not a migration — and "we support your Okta" is a sales-cycle unblock, not a feature.
- Roles: `org_admin`, `project_lead`, `analyst`, `viewer` — coarse now, resource-level grants later. Every request resolves `(user, org, project, role)` once in middleware; handlers never see cross-tenant data (RLS backstops application bugs).

## 6. AI & document processing (summary — full design in docs/03)

- **LLM:** Anthropic Claude family behind an internal `LLMProvider` interface — routing by task tier (frontier model for extraction/synthesis; small fast model for classification/triage). No LangChain: orchestration is explicit Python — pipelines here are DAGs of typed steps, and a framework's abstraction tax exceeds its value. `instructor`-style structured outputs against Pydantic schemas.
- **Parsing:** `unstructured` + format-native parsers; OCR via cloud document AI for scanned/handwritten (insurance reality), local Tesseract path for cost-sensitive/dev.
- **LLM observability:** Langfuse (self-hosted) — traces, token costs per tenant/pipeline, prompt versioning, eval logging.

## 7. Observability, monitoring, testing

- **Errors:** Sentry (web + api + worker).
- **Traces/metrics:** OpenTelemetry SDK from day 1 (FastAPI/Celery/SQLAlchemy auto-instrumentation), exported to Grafana Cloud free tier now; OTLP means the backend is swappable.
- **Logging:** structlog, JSON, request-id + tenant-id on every line. The **audit log is a product feature** (docs/04), not an ops log.
- **Testing pyramid:** pytest unit tests on domain logic and every extraction schema; API integration tests against ephemeral Postgres (testcontainers); Playwright smoke flows on the critical path (upload → model → export); **golden-set evals for AI quality (docs/03 §7) run in CI** — AI regression is a build failure, same as a broken test.

## 8. Deployment & CI/CD

**Decision: everything containerized; deploy on Render or Fly.io initially (managed Postgres + Redis + private networking); GitHub Actions for CI/CD.**

- *Why not AWS/ECS now:* it's where this lands eventually (enterprise buyers ask "which region, whose account"), but IaC + VPC + IAM engineering before design partners exist is premature. Because everything is containers + Postgres + Redis + S3, migration is re-pointing infrastructure, not re-architecting. **Trigger:** first enterprise security review requiring VPC isolation / data-residency commitments, or a BAA-equivalent ask.
- **CI on every PR:** lint (ruff, eslint), typecheck (mypy, tsc), unit + integration tests, OpenAPI client freshness check, eval suite (nightly + on prompt changes). **CD:** merge to `main` → staging; tagged release → production; migrations run as a release step with `alembic upgrade` gating deploy.
- **Environments:** local (Docker Compose: Postgres, Redis, MinIO, Langfuse), staging, production. Seeded synthetic insurance corpus so demos and tests never depend on real customer data.

## 9. Cost posture

The dominant marginal cost is LLM tokens. Controls, from day 1 because retrofitting metering is painful: per-tenant token accounting on every call (Langfuse + a `usage_events` table), task-tier model routing, aggressive caching of pipeline steps keyed on content hash (re-running a project after adding one document reprocesses one document, not the corpus), and prompt-caching for the shared ontology/context prefixes. Target: **COGS < 20% of revenue per seat** at the professional tier; the metering exists to know it, not guess it.

## 10. What would change this architecture

| Signal | Change |
|---|---|
| Pipelines grow human-in-the-loop pauses / >30 min runs | Celery → Temporal |
| Corpora >10–20M chunks or filtered-search latency degrades | pgvector → dedicated vector store behind the retrieval module |
| Deep graph analytics become a differentiator | Add Neo4j/Memgraph as a projection of the Postgres truth |
| Enterprise data-residency / private-deploy demands | Fly/Render → AWS with Terraform; single-tenant deploy profile |
| Real-time co-editing | SSE → WebSockets + CRDT layer (Yjs) on affected surfaces |
