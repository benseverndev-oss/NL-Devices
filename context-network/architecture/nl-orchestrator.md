# NL Orchestrator

The product's namesake leg: natural language → a plan (selected blocks) → the gate. The
LLM is one pluggable planner whose only freedom is to SELECT + name blocks from the closed
catalog, so it cannot hallucinate parts; whatever it emits must still pass the validator.

## Pieces (`spike/`)
- `orchestrator.py` — `run(spec, lib, planner)`: plan → `build_design` (ground-truth-aware)
  → `validate` → analytic electrical gate, with a real **feedback→retry loop** for
  feedback-aware planners. `HeuristicPlanner` (keyword router, deterministic fallback) +
  `LLMPlanner` (the seam; `block_id` is an **enum of catalog ids** — the anti-hallucination
  guard).
- `llm_client.py` — Anthropic `call_model` (`claude-opus-4-8`, forced `emit_plan` tool).
- `eval_planner.py` — scores a spec corpus + a layer-2 safety check + an attempt-≥2 recovery check.
- `codegen.py` — passing plan → `.ato`; → manufacturable BOM via `ato build`.

## ⚠️ Honest caveat (load-bearing)
The eval **defaults to a `FakeModel` that mirrors the heuristic router**, so the reported
"100% correctness / 0% hallucination" **never tested a real LLM**. `--live` hits the real
model but needs `ANTHROPIC_API_KEY` and is not run in CI. The *mechanism* (enum-constrained
seam + gate + retry loop) is proven on a 4-block catalog; it is **not** proven that a real
model plans well, nor that it scales past the toy catalog. This is the project's least
evidenced pillar — see [`GAPS.md`](../../GAPS.md) §3/§4a.

## Source of truth / specs
[`SPEC-NL-PLANNER.md`](../../SPEC-NL-PLANNER.md), [`ORCHESTRATOR.md`](../../ORCHESTRATOR.md).
Gate: [seam-validator.md](seam-validator.md).

---
**Classification:** architecture/active • **Last updated:** 2026-06-09
