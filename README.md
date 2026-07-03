# AI Transformation Copilot

An AI-powered Business Analysis and Digital Transformation platform. Organizations upload their process documentation — SOPs, process maps, meeting notes, policies, tickets — and the platform builds an evidence-linked model of how the business actually works, then generates executive-ready transformation deliverables: current/future-state process maps, requirements, AI/automation opportunity assessments, ROI models, roadmaps, and presentations.

**Positioning in one sentence:** every claim the platform makes is traceable to a source document — it is a business analyst that shows its work.

## Status

**Phase 0 — Architecture & Strategy.** No application code yet. This repository currently contains the founding design documents. Read them in order:

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

## Repository layout (planned)

```
apps/web        Next.js frontend
apps/api        FastAPI backend (REST, OpenAPI)
apps/worker     Python pipeline workers (ingestion, extraction, generation)
packages/client Generated TypeScript API client (from OpenAPI)
packages/schemas Shared extraction/deliverable JSON Schemas
infra/          Docker Compose (dev), IaC (later)
docs/           Architecture and product documents (this phase)
```
