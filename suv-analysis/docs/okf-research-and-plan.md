# OKF × the SUV project — research & plan

**Date:** 2026-06-24
**Question:** What is Google's Open Knowledge Format (OKF), and how does it
relate to the SUV "data at rest" project we just built (CSV + Python +
Turso)?

---

## 1. What OKF actually is

The **Open Knowledge Format (OKF)** is a vendor-neutral open specification
published by **Google Cloud on 12 June 2026** (currently **v0.1**). It
formalizes the "LLM-wiki" pattern: a way to hand AI agents *curated context*
about an organization's data — datasets, tables, metrics, APIs, runbooks —
without proprietary SDKs or services.

Its design philosophy, almost verbatim from the spec:

- **Just files** — a directory shippable as a tarball or git repo.
- **Just markdown** — readable in any editor, renders on GitHub.
- **Just YAML front matter** — a small block of structured, queryable fields.

### The format, precisely

- **A bundle is a directory of markdown files.** Each file is one *concept*.
- **Concept identity = file path minus `.md`.** `tables/suvs.md` → concept
  ID `tables/suvs`. Stable within the bundle.
- **Front matter** — only **`type` is REQUIRED** ("a short string identifying
  the kind of concept; consumers use it for routing, filtering, presentation").
  Recommended-but-optional: `title`, `description`, `resource` (a URI for the
  underlying asset), `tags`, `timestamp` (ISO 8601). Producers may add custom
  keys; **consumers MUST preserve unknown fields** and tolerate unknown `type`
  values.
- **Reserved filenames:** `index.md` (directory listing for progressive
  disclosure, no front matter) and `log.md` (chronological change history with
  ISO-8601 date headings). Neither may be used for concept documents.
- **Cross-references** are ordinary markdown links — **bundle-relative**
  (leading `/`, recommended) or relative. The link asserts a relationship; the
  *kind* of relationship lives in the surrounding prose. **Consumers must
  tolerate broken links** (they may be not-yet-written knowledge).

Google ships a **reference producer** (an enrichment agent that walks a
BigQuery dataset and drafts/enriches concept docs), a **reference consumer**
(a self-contained static-HTML graph visualizer), and **three sample bundles**
(GA4 e-commerce, Stack Overflow, Bitcoin).

> Spec & code: `github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf`
> (`SPEC.md`, `bundles/`, `samples/`, `src/reference_agent/`).

---

## 2. The relationship to what we built — the short version

**OKF is the formalized, agent-facing version of the exact instinct that
started this project.**

We opened with: *"a simple data-at-rest project where we don't have to use a
full-on database… basic data manipulation over files."* OKF's pitch is "just
files, just markdown, no database/SDK/runtime." Same instinct — ours aimed at
*a human with a Python script*, OKF aims at *an AI agent reading context*.

But they operate at **different layers**, and that is the key insight:

```
┌─────────────────────────────────────────────────────────────┐
│  KNOWLEDGE / CONTEXT layer   →  what an agent reads to under- │
│  (this is where OKF lives)      stand the data: schema, the   │
│                                 score's meaning, provenance   │
├─────────────────────────────────────────────────────────────┤
│  DATA-AT-REST layer          →  the actual values            │
│  (our data/suvs.csv)            (32 rows × the properties)    │
├─────────────────────────────────────────────────────────────┤
│  COMPUTE / QUERY layer       →  turns values into answers     │
│  (analyze.py, Turso view)       (the weighted off-road score) │
└─────────────────────────────────────────────────────────────┘
```

OKF holds **no row values and runs no computation** — it is metadata/semantics,
not a dataset format and not a query engine. So it does **not replace** our CSV
or Turso. It would sit *on top*, describing them so an AI agent (or a teammate)
understands what `suvs.csv` is, what the `suv_scores` view means, and why the
torsional-rigidity field is a judgement rather than a measurement.

Notably, our **`README.md` is already an informal OKF bundle** — it describes
the dataset, documents the metric and its weights, maps columns, and records
data provenance. OKF would just give that prose a *structured, agent-parseable*
shape with stable concept IDs and front matter.

---

## 3. Concept-by-concept mapping

| What we have today                         | OKF concept                                   | `type`           | Notes |
|--------------------------------------------|-----------------------------------------------|------------------|-------|
| `data/suvs.csv`                            | `datasets/used_suvs_1990_2015.md`             | `Dataset`        | OKF *describes* it; the CSV still holds the rows. `resource:` points at the CSV path. |
| Turso `suvs` table                         | `tables/suvs.md`                              | `Table`          | Body carries the column schema (the README's property table maps 1:1). |
| Turso `suv_scores` view / `analyze.py` score | `metrics/off_road_suitability_score.md`     | `Metric`         | Body explains weights, the higher/lower/band directions, and the 2350–2750 mm wheelbase sweet spot. |
| `weights.articulation.json`                | `metrics/.../profiles/articulation_first.md`  | `Scoring Profile`| Alternate weighting documented as its own concept. |
| Data-provenance caveats (README)           | `runbooks/data_provenance.md`                 | `Runbook`        | The "torsional rigidity is a 1–5 rating, verify before buying" honesty notes. |
| `build_db.sh`                              | `runbooks/rebuild_database.md`                | `Runbook`        | How to regenerate the DB; notes the `.import` meta-command gotcha. |
| `analyze.py`, `tursodb`                    | `tools/analyze_py.md`, `tools/tursodb.md`     | `Tool`           | OKF references tools via `resource:`; it doesn't run them. |

---

## 4. Proposed bundle layout (if we build it)

```
suv-analysis/okf/                         # an OKF bundle describing this project
├── index.md                              # top-level progressive-disclosure listing
├── log.md                                # change history (ISO-8601 headings)
├── datasets/
│   ├── index.md
│   └── used_suvs_1990_2015.md
├── tables/
│   ├── index.md
│   └── suvs.md                           # column schema + links to the metric
├── metrics/
│   ├── index.md
│   └── off_road_suitability_score.md     # weights/directions/sweet-spot, fully explained
├── runbooks/
│   ├── index.md
│   ├── data_provenance.md
│   └── rebuild_database.md
└── tools/
    ├── index.md
    ├── analyze_py.md
    └── tursodb.md
```

### Illustrative concept file — the metric

```markdown
---
type: Metric
title: Off-road suitability score
description: Composite 0–100 ranking of an SUV body as an off-road project base.
resource: /home/user/Mud98/suv-analysis/score_view.sql
tags: [offroad, scoring, suv]
timestamp: 2026-06-24T00:00:00Z
---

# Off-road suitability score

A weighted 0–100 score over the [suvs table](/tables/suvs.md). Each physical
property is normalised to 0–1, then combined with tunable weights.

| Property            | Weight | Direction | Rationale                          |
|---------------------|:------:|-----------|------------------------------------|
| ground_clearance_mm | 28%    | higher    | Biggest single off-road factor     |
| wheelbase_mm        | 18%    | band      | Sweet spot 2350–2750 mm            |
| weight_kg           | 14%    | lower     | Recovery, economy                  |
| …                   | …      | …         | …                                  |

Implemented identically in [analyze.py](/tools/analyze_py.md) and the
`suv_scores` SQL view; the two agree to the decimal (Wrangler TJ = 74.0).
See [data provenance](/runbooks/data_provenance.md) for the torsional-rigidity
caveat.
```

This single file is valid OKF v0.1: it has the required `type`, uses
bundle-relative links, and the body is plain markdown.

---

## 5. Why this is a good fit (and where it isn't)

**Strong fit**
- Same "just files" philosophy as our data-at-rest goal — zero new runtime,
  version-controlled next to the data, diff-able in git.
- We've *already written the content* (the README); OKF is mostly a
  restructuring, not new research.
- Makes the project legible to an AI agent: an agent handed this bundle could
  answer "which body is best and why" and "how trustworthy is the rigidity
  field" without us re-explaining.
- Cleanly separates producer (us) from consumer (any agent/tool) — we could
  later view it in Google's reference visualizer with no code on our side.

**Limits / cautions**
- **v0.1, days old.** The spec will evolve; treat it as additive, not load-
  bearing. Keep `suvs.csv` + Turso as the source of truth.
- **OKF stores no values and computes nothing** — it is not a substitute for
  the CSV or the query layer; it wraps them.
- **No standard validator yet.** "Valid OKF" today mostly means "has `type`,
  uses sane links." We'd write a tiny lint check ourselves if we want CI gating.
- **Drift risk.** Hand-authored docs can fall out of sync with the data. The
  mitigation is to *generate* the bundle from `suvs.csv` / `score_view.sql`
  (see Phase 3), mirroring OKF's own reference enrichment agent — but
  deterministic, not LLM-drafted.

---

## 6. Phased plan

- **Phase 0 — Research & decide (this document).** ✅
- **Phase 1 — Hand-author a minimal bundle** (~8 files: dataset, table, metric,
  two runbooks, index/log). Pure markdown, no tooling. Quick, demonstrates the
  fit, fully spec-valid.
- **Phase 2 — Validate.** A ~30-line `okf_lint.py` (stdlib) asserting: every
  `.md` except `index.md`/`log.md` has front matter with a `type`; links
  resolve or are intentionally pending; `index.md` files list their siblings.
  Optionally render with Google's reference visualizer to eyeball the graph.
- **Phase 3 — Generate from the source of truth.** A small generator that emits
  `tables/suvs.md` (schema) and the metric doc from `score_view.sql` + the CSV
  header, so the bundle never drifts. Wire into `build_db.sh`.
- **Phase 4 (optional) — CI/freshness.** Run the linter + regenerator in a
  SessionStart hook or CI so docs and data stay locked together.

**Effort:** Phase 1 ≈ 30 min. Phases 1–3 ≈ a half-day. All stdlib/markdown —
no new dependencies, consistent with the project's "no heavy tooling" ethos.

---

## 7. Recommendation

**Worth doing — Phase 1 now, Phase 3 if the bundle proves useful.** It's
low-cost, philosophically aligned with the project, and turns our existing
README prose into something an AI agent can consume directly. Keep it strictly
*additive*: the CSV stays the source of truth, Turso/Python stay the compute
layer, and OKF becomes the thin, portable context layer over both.

### Open questions for you
1. Want me to build the **Phase 1 bundle** now (hand-authored), or stop at this
   plan?
2. Hand-author, or go straight to a **generator** (Phase 3) that keeps the
   bundle in sync with `suvs.csv` automatically?
3. Include the `tools/` concepts (pointing at `analyze.py`/`tursodb`), or keep
   the first bundle to data concepts only (dataset/table/metric)?

---

## Sources

- [How the Open Knowledge Format can improve data sharing — Google Cloud Blog](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
- [OKF v0.1 SPEC.md — GoogleCloudPlatform/knowledge-catalog](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- [Google Cloud Announces The Open Knowledge Format — Search Engine Journal](https://www.searchenginejournal.com/google-cloud-announces-the-open-knowledge-format/579253/)
- [Open Knowledge Format (OKF): Google's New Markdown Format for AI Agents — Suganthan](https://suganthan.com/blog/open-knowledge-format/)
- [Google Cloud Introduces Open Knowledge Format (OKF) — MarkTechPost](https://www.marktechpost.com/2026/06/16/google-cloud-introduces-open-knowledge-format-okf-a-vendor-neutral-markdown-spec-for-giving-ai-agents-curated-context/)
