# 07 — UI & Design System

Target aesthetic: Linear / Vercel / Palantir Foundry — dense with information, quiet in decoration. For this product the UI *is* the trust argument: an executive judges the platform's rigor by its surfaces before reading a word. Two audiences share the app — the **analyst** (power user, keyboard-driven, lives in the review queue) and the **stakeholder/executive** (occasional, read-mostly, judges polish) — and every screen should know which one it serves.

## 1. Principles

1. **Dark mode first, light mode real.** Analysts work long sessions (dark default); exported/shared views and executive read-outs must be flawless in light. Both themes ship from M0 via tokens — retrofitting themes is misery.
2. **Evidence is always one click away.** The citation chip is the signature component; any AI-derived statement without one is a design bug.
3. **Density over whitespace theater.** Tables, queues, and canvases sized for professionals; generous spacing reserved for executive-facing summary views.
4. **Keyboard-first on analyst surfaces.** The review queue targets <10s/item median triage — j/k navigation, single-key confirm/edit/reject, `⌘K` command palette from M2.
5. **AI states are honest.** Confidence badges (high/med/low), review-state styling (AI-generated = dashed/tinted until confirmed), streaming progress with real step names from `pipeline_steps` — never a fake spinner.
6. **Accessibility is a standard, not a mode**: WCAG 2.1 AA — contrast-checked token pairs, full keyboard reachability, focus rings, reduced-motion respect, semantic landmarks. Enterprise buyers increasingly audit this.

## 2. Foundations

- **Stack:** Tailwind + shadcn/ui (owned components, docs/02 §2); tokens as CSS variables under `:root` / `[data-theme]`.
- **Color:** near-black neutral ramp (slate, not pure black), one restrained brand accent (deep violet/indigo family), and a **semantic set that carries meaning consistently everywhere**: confidence (high/med/low), review state (ai/confirmed/edited/rejected), severity (pain points, risks), horizon (roadmap buckets). Data-viz palette per the dataviz standards — categorical ≤6, colorblind-safe, identical semantics in-app and in exported decks (the deck templates consume the same tokens).
- **Type:** Inter (UI) + a mono (Geist Mono/JetBrains) for IDs, counts, code-ish data. Scale: 12/13/14 workhorse sizes, restrained display sizes for exec summaries.
- **Spacing/radius/elevation:** 4px grid; radius 6–8px; elevation by border + subtle shadow, not heavy blur. Motion: 120–180ms ease-out, purposeful only.

## 3. Information architecture

```
Org switcher ▸ Project
  ├─ Overview      (status, pipeline activity, model completeness, next actions)
  ├─ Documents     (library, upload, processing states, viewer)
  ├─ Knowledge     (entity browser · review queue · process maps)
  ├─ Opportunities (register · ROI sheets · roadmap timeline)
  ├─ Deliverables  (gallery · versions · exports)
  └─ Settings      (members, industry pack, PII policy, audit log)
```

Global: left rail nav (collapsible), `⌘K` palette, top-right pipeline-activity indicator. The project Overview is the narrative spine — "12 documents processed · 3 processes identified · 47 items awaiting review · 9 opportunities scored" with each count a link into the work.

## 4. Signature screens (design-effort priorities)

1. **Review queue (M2)** — the product's soul. Three-pane: queue list · item detail · evidence panel (source passage highlighted in document context). Bulk-confirm for high-confidence groups; progress bar toward "model validated."
2. **Process canvas (M2)** — swimlanes by actor; step nodes typed by icon (manual/system/decision/handoff); pain-point markers with severity; click → evidence panel. Read mode (clean, exec-shareable) vs edit mode (snap guides, stitch tools).
3. **Document viewer (M1)** — rendered pages with element-highlight overlay + structure sidebar; the deep-link target for every citation chip in the app.
4. **Opportunity register + ROI sheet (M3)** — scored table with impact×complexity matrix view; assumption sheet styled like a financial model (mono figures, provenance per row).
5. **Deliverable preview (M4)** — page/slide thumbnails, section-level regenerate, version diff. Must look like the artifact it produces.

## 5. Component inventory (build order)

M0: app shell, nav rail, data table, upload dropzone, dialog/toast/empty-state, theme system. M1: page renderer + highlight overlay, **citation chip**, search result card, pipeline progress (stepped). M2: review card, evidence panel, confidence + review-state badges, swimlane canvas, entity detail pane, command palette. M3: score matrix, assumption row, timeline canvas. M4: slide/page preview, section regenerate control, version diff.

## 6. Quality gates

- Every component ships both themes + keyboard path in the same PR (Storybook as the contract).
- Playwright visual snapshots on signature screens per theme.
- A quarterly "squint test" against Linear/Vercel: if a screen wouldn't survive in that company's product screenshots, it isn't done.
