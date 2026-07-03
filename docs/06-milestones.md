# 06 — Milestones (M0–M5)

Effort assumes **one senior engineer working AI-assisted, part-time (~15–20 focused hrs/week)**; calendar estimates carry that assumption. The plan optimizes for a single spine: **every milestone ends with the full upload→insight→export loop working better than the last**, never with a disconnected module. Weeks are estimates, sequencing is the commitment.

**The spine:** M0 platform skeleton → M1 documents in & searchable → M2 process model out → M3 opportunities & roadmap → M4 executive exports → M5 hardening & design partners.

---

## M0 — Foundation (Weeks 1–2)

- **Objectives:** running skeleton of the real architecture (docs/02) deployed to staging; every later milestone is features, not plumbing.
- **Deliverables:** monorepo (`apps/web`, `apps/api`, `apps/worker`, `packages/client`); Docker Compose dev env (Postgres+pgvector, Redis, MinIO, Langfuse); WorkOS auth; org/project CRUD; file upload to blob storage; CI/CD (lint, typecheck, tests, OpenAPI client check → staging deploy); Sentry + structlog + OTel wiring.
- **Architecture:** the three-deployable monolith, one dummy Celery task proving the queue + `pipeline_runs` checkpoint pattern end-to-end.
- **DB:** migrations 001–004: orgs/users/memberships, projects, documents (blob refs), pipeline_runs/steps, audit_events. RLS enabled from the first migration.
- **API:** auth callback/session; `GET/POST /orgs`, `/projects`; `POST /projects/{id}/documents` (presigned upload + registration); `GET /pipeline-runs/{id}` (SSE).
- **UI screens:** sign-in, project list, project shell (nav: Documents · Knowledge · Opportunities · Deliverables — tabs exist, later ones stubbed), document upload/list.
- **Components:** app shell + nav, design tokens (docs/07), data table, upload dropzone, toast/error surfaces.
- **Testing:** pytest + testcontainers harness; tenant-escape test (docs/05 §2) in CI from day 1; one Playwright smoke (sign in → create project → upload file).
- **Risks:** gold-plating the skeleton (mitigation: hard two-week timebox, features cut before dates); WorkOS integration friction (mitigation: it's their happy path, budget one evening).
- **Effort:** ~2 weeks. **Dependencies:** none. **Success:** a fresh clone reaches running dev env in <15 min; staging URL where a user signs in, creates a project, uploads a PDF, and sees a completed (dummy) pipeline run.

## M1 — Document Intelligence (Weeks 3–6)

- **Objectives:** the ingestion pipeline for real: any supported document in → parsed, structured, searchable, citable. Build the **golden corpus + eval harness** (docs/03 §7) *in this milestone* — quality discipline starts with the first AI feature, not after.
- **Deliverables:** parse/OCR/structure/chunk/embed pipeline (docs/03 §1) for PDF, DOCX, XLSX, PPTX, images, TXT/MD (Visio `.vsdx` stretch → M2); hybrid retrieval service; document viewer with element-level anchors; project semantic search with citations; doc classification; PII tagging pass; synthetic insurance corpus v1 (~30 docs) + extraction eval scaffold in CI.
- **Architecture:** first real pipeline DAG on the checkpoint pattern; `LLMProvider` interface + Langfuse tracing; retrieval as an internal module with a typed interface (the seam noted in docs/02 §10).
- **DB:** document_elements, chunks (vector + tsv indexes), usage_events; document supersession (docs/04 §3).
- **API:** `POST /projects/{id}/search`; `GET /documents/{id}` (structured view: elements, pages); `GET /documents/{id}/status`; pipeline progress SSE (real now).
- **UI screens:** document viewer (rendered pages + structure sidebar, anchorable elements); search screen with cited results (click-through to the exact passage); pipeline progress states on the document list.
- **Components:** PDF/page renderer with element highlight overlay, citation chip (used everywhere hereafter), search result card, processing-status indicators.
- **Testing:** parser unit tests per format against fixture files (the nastiest real-world specimens you can find — encrypted PDFs, merged-cell Excel, image-only scans); retrieval relevance evals on the golden corpus; cost assertions (token budget per document ceiling).
- **Risks:** **parsing quality is the #1 product risk** — garbage structure poisons everything downstream (mitigation: fixture-driven development, structure-recovery evals, and the corpus deliberately includes ugly documents); OCR provider cost/quality (mitigation: dual-lane design, measure both on the corpus).
- **Effort:** ~4 weeks. **Dependencies:** M0. **Success:** upload the 30-doc corpus → all parse without manual intervention; search "how are claims assigned to adjusters" returns the right passage cited to page/paragraph; eval suite runs in CI with baseline numbers recorded.

## M2 — Process Intelligence (Weeks 7–10)

- **Objectives:** the leap from searchable documents to a **Project Knowledge Model**: extraction passes, entity resolution, the analyst review loop, and the first process visualizations. This milestone is the product's soul.
- **Deliverables:** extraction passes for actors/systems/processes/steps/rules/pain-points (docs/03 §3); entity resolution with merge proposals; review queue UI (keyboard-driven triage); knowledge browser; **swimlane/process-map rendering from the PKM graph** with pain-point overlays and evidence panel; BPMN 2.0 XML export; tenant-vocabulary memory v1.
- **Architecture:** extraction as schema-versioned pipeline passes; PKM write path enforcing the evidence invariant (docs/04 — no assertion without evidence or `estimate` flag); review-resolution → eval-corpus append.
- **DB:** entities, entity_relations, evidence, review_items, entity_history; entity-type seed tables (insurance-claims pack v0).
- **API:** `GET/PATCH /projects/{id}/entities` (filter by type/review-state/confidence); `POST /entities/{id}/review` (confirm/edit/reject); `GET /review-items` + resolve; `GET /processes/{id}/graph`; `GET /processes/{id}/bpmn`.
- **UI screens:** review queue (the triage cockpit — evidence side-panel, single-key confirm/reject, bulk actions); knowledge browser (entities by type, detail panes, relation views); process map canvas (React Flow swimlanes; bpmn-js render/export); merge-proposal resolution.
- **Components:** review card + evidence panel, confidence badge, entity detail pane, swimlane canvas, pain-point overlay markers.
- **Testing:** extraction precision/recall per entity type on the golden corpus **with minimum bars enforced in CI**; entity-resolution accuracy tests; graph-render snapshot tests; review-flow integration tests (correction → PKM history → eval append).
- **Risks:** extraction quality below the trust threshold (mitigation: confidence gating means the system asks instead of asserting — a mediocre extractor with honest confidence is shippable; a good one that bluffs is not); process-graph assembly from fragmented mentions is genuinely hard (mitigation: scope v1 to section-local process assembly + analyst stitching in the canvas — assisted modeling, honestly framed, is already 10x the Visio status quo).
- **Effort:** ~4 weeks (the hardest milestone; if it slips, cut breadth of entity types, never the review loop). **Dependencies:** M1. **Success:** golden corpus → platform proposes ≥2 coherent processes; an analyst triages the review queue at <10s/item median; confirmed model renders a swimlane an insurance BA calls "recognizably our intake process"; extraction evals ≥ recorded M2 bars.

## M3 — Opportunity Engine & Roadmap (Weeks 11–14)

- **Objectives:** the "so what": scored AI/automation opportunities and a defensible roadmap, computed from the *validated* PKM.
- **Deliverables:** opportunity evaluation pass (taxonomy + versioned scoring rubric, docs/03 §5); opportunity register UI; **assumption-sheet ROI model** (AI proposes cited assumptions, analyst edits, code computes — docs/01 §2.5); roadmap generator (horizon buckets, dependencies, quick-win rule); roadmap timeline UI.
- **Architecture:** generators as the composed pattern (docs/03 §5) — this milestone establishes the generator framework M4 reuses; rubric and taxonomy as versioned data.
- **DB:** opportunities, roi_models; roadmap tables (initiatives, horizon, dependency edges).
- **API:** `POST /projects/{id}/opportunities/generate`; `GET/PATCH /opportunities`; `GET/PATCH /opportunities/{id}/roi` (assumption edits trigger recompute); `POST /projects/{id}/roadmap/generate`; `GET /roadmap`.
- **UI screens:** opportunity register (sortable/scored, rationale + evidence per row); opportunity detail with ROI assumption sheet (editable, provenance per assumption); roadmap timeline (horizon lanes, dependency arrows, quick-win highlighting).
- **Components:** score visualization (impact×complexity matrix), assumption row editor, timeline/Gantt-lite canvas, rationale disclosure.
- **Testing:** rubric determinism tests (same PKM + same rubric version → same scores); ROI arithmetic unit tests (pure functions, exhaustive); opportunity-quality eval (LLM-judge rubric, human-audited sample); integration: edit assumption → figures update everywhere.
- **Risks:** generic McKinsey-slop recommendations (mitigation: opportunities must bind to specific PKM pain points with evidence — no free-floating "adopt AI chatbots"; the insurance pack's heuristics carry your practitioner depth); ROI credibility (mitigation: the assumption sheet *is* the mitigation — nothing unexplained reaches a slide).
- **Effort:** ~4 weeks. **Dependencies:** M2. **Success:** on the golden corpus, ≥70% of generated opportunities rated "credible, would present" by you acting as the skeptical reviewer; every ROI figure click-traces to assumptions; roadmap respects declared dependencies.

## M4 — Deliverable Studio & Exports (Weeks 15–18)

- **Objectives:** the payoff moment — executive-quality artifacts leaving the platform: PPTX deck, Word/PDF assessment report, BPMN/Visio-compatible diagrams, Excel backlog.
- **Deliverables:** deliverable spec + immutable versioning (docs/04); generators: executive summary, current-state assessment (BRD-style), opportunity register export, roadmap deck; PPTX engine (`python-pptx` on designed templates: charts, timelines, process diagrams, speaker notes); DOCX/PDF engine (`docxtpl` + WeasyPrint); XLSX backlog export; citation appendix in every export; deliverable review/regenerate UI with version diffing.
- **Architecture:** rendering as pure functions of `deliverable_versions.spec`; template gallery as pack data (industry packs, docs/03 §6); export rendering in workers (long-running), streamed progress.
- **DB:** deliverables, deliverable_versions, template registry.
- **API:** `POST /projects/{id}/deliverables` (type + options); `GET /deliverables/{id}/versions`; `POST /deliverables/{id}/regenerate`; `GET /versions/{id}/download`.
- **UI screens:** deliverable gallery (type picker + template previews); deliverable detail (section-level preview, per-section regenerate, version history + diff); export/download flow.
- **Components:** deck/page preview renderer, section editor with regenerate, version diff view, template cards.
- **Testing:** golden-file rendering tests (spec fixture → byte-stable-ish artifact, structural assertions on the PPTX/DOCX XML); citation-coverage checks (every generated assertion carries evidence or `estimate`); numeric-integrity checks (every figure in the deck exists in an ROI model); manual design QA against the docs/07 bar.
- **Risks:** **PPTX quality is where "enterprise-grade" is judged in five seconds** (mitigation: invest in 2–3 genuinely designed templates — hire a deck designer for a few hundred dollars if needed — rather than 10 mediocre ones; deterministic layout, LLM only writes prose); template-engine edge cases (mitigation: golden-file tests, constrain layouts).
- **Effort:** ~4 weeks. **Dependencies:** M3 (generator framework, ROI data). **Success:** **the full demo** — synthetic corpus upload → review → opportunities → export, producing a deck you would genuinely present to an executive committee without touching PowerPoint; a BA who has never seen the product completes the loop unassisted on a fresh project.

## M5 — Hardening & Design Partners (Weeks 19–24)

- **Objectives:** convert a working product into a trustworthy one, and put it in 3–5 outside analysts' hands on real engagements.
- **Deliverables:** onboarding polish (empty states, sample project, guided first-run); org admin (member management, roles, audit log viewer); billing scaffold (Stripe, seat-based, trial); security-questionnaire package finalized from docs/05 (+ automated pen-test pass and fixes); performance work on large corpora (500+ docs: batching, cache hit-rates, queue tuning); eval expansion from design-partner corrections; feedback instrumentation (per-deliverable quality rating, correction analytics); PII redaction policy UI.
- **Architecture:** no new subsystems — this milestone deliberately adds *zero* architectural surface; it pays down everything M1–M4 deferred.
- **DB:** billing/subscription tables; feedback tables; index/perf passes from real load.
- **API:** admin endpoints (members, roles, audit query); billing webhooks; feedback capture.
- **UI screens:** onboarding flow, org settings/admin, audit log viewer, billing screens.
- **Testing:** load test (500-doc project ingestion under an hour, UI responsive throughout); restore-from-backup drill (docs/05 §5); full Playwright coverage of the critical path; security regression suite.
- **Risks:** design-partner recruitment stalls (mitigation: start recruiting during M3 from your own network — consultants and BA community, per docs/01 §2.4; the M4 demo is the recruiting asset); real-world documents break parsing in new ways (mitigation: that's the point — every breakage becomes a fixture; budget explicit triage time weekly).
- **Effort:** ~6 weeks. **Dependencies:** M4; partner recruiting starts M3. **Success:** ≥3 design partners each complete a real engagement deliverable through the platform; ≥1 platform-generated artifact presented to a real executive audience; a completed security questionnaire sent to a prospect; retention signal — partners start a *second* project unprompted.

---

## Deferred backlog (post-M5, demand-ordered — see docs/01 §3)

Meeting/audio intelligence · executive dashboard & KPI tracking · Jira/Confluence/Notion write-back integrations · future-state process designer (current-state editing exists; greenfield design is a bigger canvas problem) · requirements copilot extensions (test cases, SQL/API suggestions, wireframes) · second industry pack (healthcare, via a design partner) · real-time collaboration · single-tenant enterprise deploy profile · SOC 2 Type II.

## Program-level risks

| Risk | Watch signal | Response |
|---|---|---|
| Scope creep back toward the 10-module vision | A milestone adds a screen not on the spine | The deferral list is a contract with yourself; new ideas go to the backlog, not the sprint |
| Founder bandwidth (day job) | Two consecutive weeks <10 hrs | Re-cut milestone breadth (fewer entity types, fewer templates) — never cut evals, review loop, or the export bar |
| AI cost per project exceeds price point | usage_events COGS per golden-corpus run trending up | Tier routing, caching, prompt-caching audits (docs/02 §9); it's measured from M1 precisely so this is caught early |
| Trust failure at a design partner (bad extraction shown to their client) | Any confirmed-state error reaching an export | Post-mortem into eval corpus; tighten confidence gates; this is the one failure mode treated as a sev-1 |
