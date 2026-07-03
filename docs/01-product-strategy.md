# 01 — Product Strategy

This document does two jobs: it states the strategy, and it pushes back on the parts of the original vision that would sink the company if taken literally. You asked to be challenged; this is where it happens.

---

## 1. The thesis (kept intact)

Business analysis and transformation consulting is a **$300B+ labor market** whose core work product is: read a large pile of unstructured organizational knowledge → build a mental model of the current state → identify improvement opportunities → produce executive deliverables. Every step is document-heavy, pattern-based, and judgment-gated — which is precisely the shape of work LLMs amplify best.

The consultancies (McKinsey, Deloitte, Accenture) sell this as a service at $300–600/hour. The tools BAs actually use (Visio, Confluence, Excel, PowerPoint) are dumb containers. There is no product that sits between them: **software that does the analysis, with a human analyst steering it.** That gap is real and the timing is right.

## 2. The assumptions I'm challenging

### 2.1 "Palantir + McKinsey + Copilot combined" is a positioning statement, not a product plan

The vision lists **10 major modules and ~35 output types**. Every successful enterprise platform started as a wedge: Palantir started as fraud/intel link analysis, Figma as a browser vector editor, Datadog as server monitoring. A solo founder (with a day job) shipping 10 modules ships 10 demos and zero products.

**Counter-proposal — the wedge:**

> **Upload your process documents → get a validated, evidence-linked current-state process model and an AI/automation opportunity roadmap → export the executive deck.**

That is Modules 2 (Document Intelligence), 4 (Process Intelligence), 6 (Opportunity Engine), 8 (Roadmap), and a thin slice of 9/10 (exports) — composed into **one workflow with one "wow" moment**. Modules 3 (Meeting Intelligence), 7 (Dashboards), and the full Requirements Copilot come later, and the architecture (docs/02) keeps their doors open.

**Why this wedge specifically:**
- It's the highest-pain, highest-fee part of a transformation engagement (the "current state assessment" phase — typically 6–12 weeks of consultant time, $150k–500k).
- It's demoable in 15 minutes with a customer's own documents. Nothing sells like their own SOPs coming back as a swimlane diagram with pain points flagged.
- It produces the platform's core asset — the **organizational knowledge model** — which every later module reads from. Building it first is also the correct engineering order.

### 2.2 "The platform automatically understands everything" is the wrong promise

No system reliably auto-understands a messy insurance operation from documents alone, and — more important — **no executive trusts one that claims to.** The credible promise is different and better:

> The platform produces a *draft* understanding in hours instead of weeks, shows the evidence behind every element, and makes a senior BA 10x faster at validating and completing it.

This reframing is not a retreat; it's the moat. "Fully automatic" outputs are a commodity any wrapper can fake in a demo. **Evidence-linked, analyst-validated outputs** are defensible, auditable (which insurance/GRC buyers require), and they generate the correction data that makes the product smarter per customer. Human-in-the-loop review is a first-class feature with UI, state, and audit — not an apology.

### 2.3 Meeting Intelligence should be cut from v1

Transcription + summaries + action items is a knife-fight commodity: Teams Copilot, Zoom AI, Gemini, Otter, Fireflies all ship it free-with-suite. You cannot win there and don't need to — **accept transcripts as an input document type** (they're just documents) and skip audio processing entirely in v1. Revisit only when customers ask for requirements-extraction-from-recordings specifically, which is a genuinely differentiated slice.

### 2.4 The buyer is not who the vision implies

"A company uploads its SOPs" assumes a self-serve enterprise buyer. Enterprises don't upload their claims SOPs to a new vendor's website. Sequenced honestly:

1. **First user: you.** Deploy it on your own BA work in insurance. Every deliverable you produce at your job is a live case study and a dogfooding cycle. This is also the career-leverage play — you become the BA whose assessments take days, not months.
2. **First customers: boutique consultancies and independent BAs/transformation PMs** (10–200 person firms). They have the pain (fixed-fee engagements, deadline pressure), the documents in hand, low procurement friction, and they'll pay $200–500/user/month because it's priced against billable hours. They are also a **channel**: their deliverables land on enterprise desks.
3. **Then: transformation offices at mid-market insurers** (via the consultants and your network), where security review (docs/05) becomes the gate. This is when SSO/SCIM/audit certifications pay for themselves.

### 2.5 ROI numbers are the most dangerous output

The vision lists "ROI calculations / cost savings" as an automatic output. An LLM inventing dollar figures in an executive deck is how you lose a customer permanently. ROI must be a **transparent, deterministic model**: the AI proposes assumptions (volumes, handle times, loaded rates — each cited to a source or flagged as an estimate), the analyst edits them, arithmetic is computed in code, and every figure in the deck traces to the assumption sheet. Same principle for anything quantitative: **LLMs propose, code computes, humans approve.**

### 2.6 "Insurance + 8 other industries" — pick one, architect for many

Sell insurance-only for the first year. Domain depth (claims terminology, guidewire/duck-creek awareness, regulatory context) is a differentiator; nine shallow verticals is a spec sheet. Architecturally, industries are **industry packs** — ontology terms, prompt overlays, deliverable templates, benchmark data — loaded as data, not code (docs/03 §6). Adding healthcare later is a content project, not a rewrite.

## 3. What the product actually is (v1 definition)

**Input:** a project workspace where a BA uploads engagement documents (PDF, DOCX, XLSX, PPTX, Visio, images, transcripts, CSV exports from Jira/ServiceNow).

**The platform builds:** an evidence-linked **Project Knowledge Model** — processes, steps, actors, systems, business rules, pain points, risks, metrics — every element carrying citations to source passages and a confidence level, every element reviewable (confirm / edit / reject) by the analyst.

**Output (generated from the validated model, never straight from raw text):**
- Current-state process maps (swimlane / BPMN 2.0) with pain-point overlays
- AI & automation opportunity register, scored (impact, complexity, risk) with a transparent ROI model
- Transformation roadmap (30/90/180/365-day horizons, quick wins vs. structural)
- Executive summary and PowerPoint export; BRD-style document export (Word/PDF)

**Explicitly deferred:** meeting/audio processing, live dashboards, Jira/Confluence write-back, wireframes/test cases/SQL generation, multi-industry packs, real-time collaboration.

## 4. Moat — why this survives "GPT-6 does it in a prompt"

1. **The knowledge model + review workflow.** A chat model produces prose; this produces a *structured, versioned, validated* model of an organization that deliverables regenerate from. Switching cost compounds as the model accretes.
2. **Evidence discipline.** Citation-per-claim across 500 documents is systems engineering (chunking, provenance tracking, entity resolution), not prompting.
3. **Domain depth.** Insurance ontology + deliverable templates that match how carriers actually run claims. Encoded practitioner knowledge — your knowledge — that a horizontal tool doesn't have.
4. **Correction flywheel.** Every analyst edit is labeled training/eval data for extraction quality, per-tenant vocabulary, and benchmarks ("manual data re-entry appears in 78% of claims intake processes").
5. **Trust surface.** Audit logs, versioned deliverables, tenant isolation — the boring stuff consultancies and carriers require and chat tools lack.

## 5. Commercial direction (held loosely until design partners exist)

- **Packaging:** per-seat professional tier for consultants/BAs (~$200–400/user/mo) + per-project or platform tier for enterprises (5-figure annual). Usage-based AI cost pass-through above a fair-use threshold protects margin against token burn.
- **Land:** a single engagement/assessment. **Expand:** the knowledge model makes the second engagement cheaper, then the transformation office adopts it as the system of record for process knowledge.
- **Near-term success metric (pre-revenue):** 3–5 design partners running a real engagement through the platform, and one deliverable produced by it that ships to a real executive audience. That beats any feature count.

## 6. Strategic risks, stated honestly

| Risk | Mitigation |
|---|---|
| Solo founder + day job → scope death | The wedge (§2.1); milestones sized in docs/06; ruthless deferral list (§3) |
| Incumbent suites (Microsoft, Celonis, IBM Blueworks) add "AI process analysis" | They sell to IT with process-mining event logs; we sell to the analyst with documents. Speed + domain depth + deliverable quality. Ship before the window narrows. |
| Extraction quality below trust threshold | Eval harness from M1 (docs/03 §7); confidence gating — low-confidence items are queued as questions for the analyst, not asserted |
| Insurance data sensitivity blocks pilots | PII-aware handling from M1, security narrative early (docs/05); pilot with redacted/synthetic corpora when needed |
| Employer IP conflict with the day job | **Action item, not a footnote:** review employment IP agreement; build on personal time/equipment; keep employer documents out of the system entirely. Resolve before the first external user. |
