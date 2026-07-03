# 03 — AI Architecture

The AI system's job is **not** "answer questions about documents." It is to construct a structured, evidence-linked **Project Knowledge Model (PKM)** from an unstructured corpus, and to generate deliverables *from that model* — never directly from raw text. This two-stage design is the central architectural commitment; everything else follows from it.

```
 Documents ──► Ingestion ──► Extraction ──► PKM (Postgres) ──► Generation ──► Deliverables
                pipeline       (schemas,      entities +          (composed      (docs, decks,
                (parse/OCR/     citations,     relations +         generators     diagrams,
                 chunk/embed)   confidence)    evidence            over the       roadmaps)
                                               + review state      validated
                                                                   model)
                                    ▲                                   
                                    └────────── Analyst review loop ────┘
                                        (confirm / edit / reject → eval data)
```

**Why two stages instead of "RAG straight to deliverable":** a BRD generated directly from retrieval is unauditable prose — change one source document and nothing downstream knows. With the PKM in between, deliverables are *renderings of reviewed facts*: regenerable, diffable, citable, and consistent with each other (the process map and the BRD can't disagree, because they read the same model).

## 1. Ingestion pipeline

A DAG of idempotent, checkpointed steps (Celery tasks; state in `pipeline_runs`/`pipeline_steps`):

1. **Detect & route** — MIME/type detection → format-specific parser (`PyMuPDF` for PDF, `python-docx`, `openpyxl`, `python-pptx`, `unstructured` fallback; Visio `.vsdx` is Open Packaging XML — parse shapes/connectors natively into diagram structure, a differentiator nobody handles well).
2. **OCR lane** — scanned/image PDFs and images route to a document-AI OCR provider (insurance corpora are full of scanned forms and faxes; this lane is not optional). Confidence per block is retained.
3. **Structure recovery** — headings, tables (kept as structured tables, not flattened prose), lists, figures. Every element gets a stable `element_id` and page/coordinate provenance → this is what makes citations clickable later.
4. **Chunking** — structure-aware (respect section boundaries; tables and diagram-derived structures stay atomic), ~500–1,000 token targets with metadata (doc, section path, page, element ids).
5. **Enrichment & indexing** — embeddings (pgvector), lexical index (tsvector), document-level classification (SOP / policy / org chart / meeting notes / ticket export / process map) which conditions later extraction prompts.
6. **PII pass** — detect and tag PII/PHI spans at ingestion (docs/05 §4); tags flow with chunks so prompts and exports can redact by policy.

Steps cache on `(content_hash, step_version)` — adding one document to a 300-doc project reprocesses one document.

## 2. Retrieval

Hybrid retrieval as a single internal service used by both chat-style Q&A and extraction: vector + BM25 with reciprocal-rank fusion, reranking (small-model reranker) when candidate sets are large, and **filterable by knowledge-model context** (e.g., retrieve only within documents linked to the Claims Intake process). Retrieval returns `element_id`-level provenance, never bare text — the citation chain must survive every hop.

## 3. Extraction — building the knowledge model

Extraction runs as **schema-driven passes** over the corpus, each pass a Pydantic schema the LLM must fill via structured output, each extracted item carrying `evidence: list[ElementRef]` and `confidence: high|medium|low`.

Core passes (v1): **Actors & org structure · Systems · Processes & steps** (step type: manual/system/decision/handoff; inputs/outputs; sequencing) **· Business rules & decisions · Pain points / waste / rework** (tagged with a Lean-derived taxonomy: waiting, rework, motion/handoffs, overprocessing, defects…) **· Risks & compliance obligations · Metrics & volumes** (numbers are extracted with units + source — they feed the ROI model, so provenance is mandatory).

Design rules that keep extraction trustworthy:
- **Entity resolution is its own step**: "FNOL team," "First Notice of Loss dept," and "intake" must merge to one actor. Deterministic normalization + embedding similarity proposes merges; ambiguous merges become **analyst questions**, not silent guesses. This is the difference between a knowledge model and a pile of tags.
- **Confidence gating**: `high` items assert into the model (still reviewable); `medium/low` items enter the **review queue as questions** ("Is 'CMS' here the claims management system or a regulator?"). The system asks rather than hallucinates — with an insurance-expert user, questions are cheap and wrong assertions are expensive.
- **Ontology-guided, not ontology-limited**: prompts carry the industry pack's ontology (§6) as vocabulary and hints, but extraction may emit out-of-ontology entities flagged as `novel` — real orgs never match the textbook.

## 4. The analyst review loop

Every PKM element has review state: `ai_generated → confirmed | edited | rejected`. The review UI (docs/07) is built for speed — keyboard-driven triage of the queue, side-by-side evidence panel, bulk confirm on high-confidence groups. Three products fall out of one interaction:
1. The **validated model** deliverables are generated from (generators can weight or filter on review state; the executive deck defaults to confirmed-only content, clearly labeled).
2. **Eval data**: every correction is a labeled example appended to the golden set (§7).
3. **Tenant memory**: confirmed vocabulary (this org's system names, team names, acronyms) feeds back into extraction prompts for subsequent documents in that tenant. Per-tenant only — no cross-customer leakage.

## 5. Generation — deliverables as composed generators

Each deliverable type is a **generator**: `(PKM slice, template, options) → artifact + citation map`. Generators share a composition pattern — deterministic assembly where possible, LLM synthesis only where prose is genuinely needed, and *all numbers computed in code*:

- **Process maps / BPMN / swimlanes** — mostly deterministic: PKM process graph → layout → BPMN 2.0 XML + React-Flow JSON. The LLM proposed the graph during extraction; drawing it is not an LLM job.
- **Opportunity register** — per-process evaluation pass against an **opportunity taxonomy** (GenAI, agents, RPA, document AI, decision engine, workflow redesign, elimination). Scoring rubric (impact, complexity, risk, time-to-value) is explicit and versioned; scores come with rationale + evidence.
- **ROI model** — LLM proposes assumptions (each cited or flagged `estimate`), analyst edits them in an assumption sheet, **arithmetic is code**. Deck figures link back to assumptions. (Strategy rationale: docs/01 §2.5.)
- **Roadmap** — sequencing over scored opportunities with dependency and capacity constraints; horizon buckets (30/90/180/365); quick-win identification is a rule (high impact × low complexity), not a vibe.
- **Documents & decks** — templated (`docxtpl`, `python-pptx`) with LLM-written narrative sections; templates carry the professional layouts, so quality is designed once, not sampled per run. Exports embed a citation appendix.

Long generations stream over SSE; a failed section retries alone (generators are step-checkpointed like pipelines).

## 6. Industry packs

A pack is **data, not code**: ontology (entity types, canonical actors/systems/process names for the vertical), extraction prompt overlays, pain-point/opportunity heuristics, deliverable templates and executive language, benchmark ranges. V1 ships `insurance-claims` (deep, authored from your own expertise — this is where practitioner knowledge is encoded); the pack loader is generic from day 1 so healthcare later is authorship, not engineering.

## 7. Evaluation — the AI quality system

This is the discipline that separates an enterprise product from a demo:

- **Golden corpus**: a synthetic-but-realistic insurance claims document set (built in M1, grown from anonymized review corrections) with hand-labeled expected extractions.
- **Extraction metrics**: precision/recall per entity type, citation validity (does the evidence span actually support the claim — checked by an LLM judge + spot audits), entity-resolution accuracy, calibration (do `high` confidence items deserve it).
- **Generation checks**: schema validity, citation coverage (% of assertions with evidence), numeric-integrity (every figure traces to the assumption sheet), rubric-scored deliverable quality (LLM judge with a versioned rubric, human-audited monthly).
- **Operationally**: evals run nightly and on any prompt/schema/model change; results in Langfuse; a regression beyond threshold **fails CI**. Prompts are versioned artifacts in the repo, not strings in code.

## 8. Model strategy & cost

- Task-tier routing behind the `LLMProvider` interface: frontier model (Claude Opus-class) for extraction and executive synthesis; fast small model (Haiku-class) for classification, triage, reranking assists. Model IDs are config, per-task, so upgrades are an eval run + config change.
- Prompt caching for the stable prefix (ontology + instructions) across a corpus run — extraction passes share ~80% of their prompt.
- Per-tenant, per-pipeline token accounting (`usage_events`) → COGS per project is a dashboard number, not a surprise.
- **No fine-tuning in v1.** The leverage order is: better parsing > better schemas > better retrieval > tenant memory > fine-tuning. Revisit only when eval data shows a plateau that few-shot + ontology can't move.
