---
name: regjeringen-ingestion
description: Build and maintain the Sculpin regjeringen.no ingestion module. Use when Codex needs to implement source audits, hearing parsers, canonical provenance models, crawler policy, raw storage, graph mapping, parser fixtures, data quality checks, or Sculpin agent tools for Norwegian government document ingestion.
---

# Regjeringen Ingestion

## Overview

Use this skill to keep implementation work aligned with `devel_plan.md`. Optimize for a hearing-only MVP first: source audit, fixtures, deterministic parser, canonical model, field-level provenance, and graph-safe exports.

## Workflow

1. Read `devel_plan.md` sections relevant to the requested task.
2. Check `AGENT.md` for project operating rules.
3. Keep work scoped to the current phase unless the user explicitly broadens scope.
4. Add or update fixtures before changing parser behavior.
5. Preserve source pointers and field-level provenance in every model or export change.
6. Run focused tests for the affected module and report any skipped validation.

## Phase Guidance

- For source audit tasks, inspect robots, sitemap, category listings, detail-page structure, attachment patterns, language variants, and hearing response risk.
- For parser tasks, prefer deterministic selectors and heading-aware extraction. Use fallback extraction only after fixture evidence shows the deterministic path is insufficient.
- For crawler tasks, enforce robots policy, disallowed query keys, conservative concurrency, retries, checksums, and clear user agent configuration.
- For storage tasks, keep raw artifacts immutable and content-addressed. Store source URLs, final URLs, headers, timestamps, parser versions, and checksums.
- For graph tasks, export metadata and source pointers only. Do not dump full text or complete PDF/DOCX contents into the graph.
- For AI extraction tasks, require source spans, confidence, model/prompt/schema versions, and proposed review status.

## Local References

- Read `references/mvp-checklist.md` when planning or reviewing source-audit, hearing-parser, graph-export, or Sculpin tool work.
