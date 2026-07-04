# AI Transformation Copilot

An AI-powered Business Analysis and Digital Transformation platform. Organizations upload their process documentation — SOPs, process maps, meeting notes, policies, tickets — and the platform builds an evidence-linked model of how the business actually works, then generates executive-ready transformation deliverables: current/future-state process maps, requirements, AI/automation opportunity assessments, ROI models, roadmaps, and presentations.

**Positioning in one sentence:** every claim the platform makes is traceable to a source document — it is a business analyst that shows its work.

## Status

**M2 — Process Intelligence: shipped.** The Project Knowledge Model is live: extraction passes turn processed documents into actors, systems, processes with ordered steps, business rules, and taxonomy-tagged pain points — every assertion carrying evidence (enforced in the write path, verified in evals at 100% coverage). Low-confidence extractions and entity-merge questions land in a keyboard-driven review queue (j/k/c/x); analyst confirmations, edits, rejections, and merges are versioned in entity history, and re-extraction never clobbers reviewed work. Processes render as swimlane canvases (lanes by actor, pain-point overlays, evidence panel) and export as interoperable BPMN 2.0 XML. Extraction runs ontology-driven from the insurance-claims industry pack locally, or via Claude when a key is configured — same validation either way. Next: **M3 — Opportunity Engine & Roadmap** (docs/06).

*M1 — Document Intelligence: shipped.* The ingestion pipeline is real: PDF/DOCX/XLSX/PPTX/TXT/MD parse into structured, provenance-carrying elements; documents are classified, PII-tagged, chunked structure-aware, and embedded (pgvector). Hybrid retrieval (vector + lexical, RRF-fused) powers project search where **every hit cites its exact source passage** and deep-links into the document viewer. A 12-document synthetic insurance-claims corpus plus golden eval bars (retrieval hit-rate, classification accuracy, PII recall) run in CI — AI regression fails the build. AI providers sit behind interfaces: deterministic local implementations for dev/test, Voyage embeddings + Claude via config (`ATC_EMBEDDING_PROVIDER=voyage`, `ATC_ANTHROPIC_API_KEY`), with per-call usage metering. Next: **M2 — Process Intelligence** (docs/06).

*M0 — Foundation: shipped.* Auth, workspaces, projects, presigned uploads, checkpointed pipelines, RLS tenant isolation with tenant-escape tests, append-only audit log.

### Run it locally

```sh
make setup      # python venv (uv) + pnpm workspace
make infra-up   # postgres + redis + minio via docker compose
cp .env.example apps/api/.env
make migrate
make api        # :8000
make worker     # celery worker (second terminal)
make web        # :3000 (third terminal)
```

Sign in at http://localhost:3000 with any email (dev auth mode), create a project, drop a PDF on the Documents tab, and watch the pipeline take it to `ready`.

```sh
make test       # pytest against real Postgres (incl. tenant-escape tests)
make lint typecheck
make client     # regenerate OpenAPI schema + typed TS client
```

## Design documents

Read them in order:

| Doc | Contents |
|---|---|
| [docs/01-product-strategy.md](docs/01-product-strategy.md) | Market thesis, the wedge, challenged assumptions, buyer analysis, moat, pricing direction |
| [docs/02-system-architecture.md](docs/02-system-architecture.md) | System design, technology stack with justifications and tradeoffs, deployment, scaling path |
| [docs/03-ai-architecture.md](docs/03-ai-architecture.md) | Ingestion pipeline, extraction schemas, RAG + knowledge model, deliverable generation, evaluation |
| [docs/04-data-model.md](docs/04-data-model.md) | Domain model, core tables, multi-tenancy, versioning, audit |
| [docs/05-security-and-enterprise-readiness.md](docs/05-security-and-enterprise-readiness.md) | Tenant isolation, authN/Z, data handling, compliance sequencing |
| [docs/06-milestones.md](docs/06-milestones.md) | M0–M5 delivery plan: objectives, deliverables, schema/API/UI scope, testing, risks, effort, success criteria |
| [docs/07-ui-design-system.md](docs/07-ui-design-system.md) | UI philosophy, design tokens, core screens, component inventory |

## Core principles

1. **Evidence over eloquence.** Generated deliverables cite their sources. An unverifiable insight is a liability in front of an executive.
2. **Human-in-the-loop is the product, not a fallback.** The BA reviews, corrects, and approves; the platform learns the org's vocabulary from those corrections.
3. **Wedge first, platform second.** V1 is the best tool in the world for one job — turning a pile of process documents into a validated current-state model and an AI-opportunity roadmap for insurance operations. The ten-module platform is the destination, not the starting line.
4. **Enterprise-grade from the first commit** where retrofitting is expensive (multi-tenancy, audit log, typed contracts), pragmatic everywhere else.

## Repository layout

```
apps/web         Next.js 15 frontend (Tailwind v4, dark-first tokens, TanStack Query)
apps/api         FastAPI backend — modules/{accounts,auth,projects,documents,pipelines}
apps/worker      Celery entrypoint over the same Python codebase (see its README)
packages/client  TypeScript types generated from the API's OpenAPI schema
packages/schemas openapi.json (source of truth for the client; CI checks freshness)
infra/           Docker Compose for dev dependencies
docs/            Architecture and product documents
```
