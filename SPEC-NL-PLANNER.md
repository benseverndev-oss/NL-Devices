# Spec — Make the NL Planner Real (Gap #1)

> Implementation spec for the top gap in [`GAPS.md`](./GAPS.md) §5: turn the
> project's namesake — *natural language* → design — from a keyword router into a
> real, validator-gated LLM planner. Status: **spec / not yet built.**
>
> Scope is deliberately narrow because the hard scaffolding already exists:
> `orchestrator.py` has the `LLMPlanner` seam, the enum-constrained `emit_plan`
> tool, and the `call_model(system, user, tools)` contract. This spec fills the
> three things that are missing or overclaimed, and adds the eval that proves it.

---

## 1. Goal & definition of done

**Goal:** a real Claude model selects + wires verified blocks from the closed
catalog for a natural-language spec; the deterministic gate still owns
correctness; an unsatisfiable/unsafe plan is rejected, and the model gets the
validator feedback and retries.

**Done when all hold:**
1. `LLMPlanner` runs against a real `claude-opus-4-8` client and produces a plan
   for the existing demo specs (parity with `HeuristicPlanner` on those).
2. `run()` implements an **actual feedback→retry loop** (today it doesn't — see §3).
3. A **15–20 spec eval set** runs offline-mockable in CI and reports
   plan-correctness; against a real key it reports the live pass rate.
4. The two anti-hallucination layers are intact and tested: the model **cannot**
   name a part outside the catalog (enum), and whatever it emits **still passes
   the gate** or is rejected.
5. No API key in the environment? The whole thing still imports, the heuristic
   path still runs, and the eval runs against a deterministic fake model.

**Explicitly NOT in this spec:** richer block library / a real MCU (that's
GAPS §5 item 2, separate), datasheet extraction, UI, fab export.

---

## 2. Current state (what's already here vs. missing)

| Piece | State | Evidence |
|---|---|---|
| `LLMPlanner` class, prompt builder, enum `emit_plan` tool | ✅ exists | `orchestrator.py:94-149` |
| `call_model(system, user, tools)` injection seam | ✅ exists, **never wired** | `orchestrator.py:98,142-147` — `call_model=None` → raises |
| `plan(spec, lib, feedback=…)` accepts feedback | ✅ param exists | `orchestrator.py:142` |
| **Actual retry loop** that passes feedback back | ❌ **missing** | `run()` calls `planner.plan(spec, lib)` once, no feedback, no loop (`orchestrator.py:154`) |
| Real Anthropic client (`call_model` impl) | ❌ missing | nothing imports `anthropic` |
| Eval set + metric | ❌ missing | only 4 inline demo specs |
| Offline test path (no key) | ⚠️ partial | heuristic runs; no fake-model test of the LLM seam |

So the work is: **(a)** write `call_model`, **(b)** make `run()` actually loop on
feedback, **(c)** build the eval + fake model, **(d)** wire CI.

---

## 3. Design

### 3a. The model client — `spike/llm_client.py` (new)

A single function matching the existing seam contract. Uses the official
Anthropic Python SDK (`pip install anthropic`), model **`claude-opus-4-8`**,
credentials from `ANTHROPIC_API_KEY` (the default `anthropic.Anthropic()`
resolution — never hardcode a key).

```python
"""Anthropic-backed call_model for LLMPlanner. The model's ONLY freedom is to
select+name blocks via the emit_plan tool; tool_choice forces that tool, and its
block_id enum is the catalog (anti-hallucination layer 1)."""
from __future__ import annotations
import anthropic

MODEL = "claude-opus-4-8"

def make_call_model(client: anthropic.Anthropic | None = None, *, max_tokens: int = 2048):
    client = client or anthropic.Anthropic()   # reads ANTHROPIC_API_KEY

    def call_model(system: str, user: str, tools: list[dict]) -> dict:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            tool_choice={"type": "tool", "name": tools[0]["name"]},  # force emit_plan
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == tools[0]["name"]:
                return block.input           # -> {"instances": [...]} (LLMPlanner contract)
        raise RuntimeError(f"model did not call {tools[0]['name']}: stop={resp.stop_reason}")

    return call_model
```

**Decisions (with rationale):**
- **`tool_choice` forces `emit_plan`** → the model must return structured block
  selections, never prose. Combined with the existing `block_id` enum, the model
  *cannot* emit a part outside the verified library.
- **Thinking omitted in v1.** Selecting from a ≤10-block catalog is not a
  reasoning-heavy task, and forcing a specific tool is the cleanest guarantee of
  structured output. *If* plans later get complex (multi-bus, constraints), switch
  to `thinking={"type":"adaptive"}` **and** `tool_choice={"type":"auto"}` (forced
  single-tool choice and thinking can conflict), leaning on the gate to catch
  anything the freer model gets wrong. Note this as a documented follow-up, not v1.
- **No streaming** (`max_tokens` is small; one tool call). The SDK auto-retries
  429/5xx.
- Returns `block.input` verbatim — exactly what `LLMPlanner.plan` already expects
  (`orchestrator.py:148`), so **no change to `LLMPlanner` is required** beyond
  what's there.

### 3b. The retry loop — fix `run()` in `orchestrator.py`

This is the overclaimed piece (ORCHESTRATOR.md says the loop is "wired"; it
isn't). Make `run()` actually iterate, feeding the gate's messages back to a
planner that accepts `feedback`:

```python
def run(spec, lib, planner, *, max_attempts=3):
    feedback = None
    for attempt in range(max_attempts):
        try:
            plan = planner.plan(spec, lib, feedback) if _accepts_feedback(planner) \
                   else planner.plan(spec, lib)
        except TypeError:                      # HeuristicPlanner.plan(spec, lib)
            plan = planner.plan(spec, lib)
        design = bc.build_design(plan, lib)
        res = sv.validate(design)
        res["electrical"] = electrical.check_electrical(plan, lib)
        ok = not any(res.values())
        if ok or not _accepts_feedback(planner):
            return plan, design, res, ok, attempt + 1
        feedback = _format_feedback(res)        # gate messages -> next prompt
    return plan, design, res, ok, max_attempts
```

`_format_feedback(res)` flattens the gate's per-check message lists into the text
that `LLMPlanner.messages(spec, lib, feedback=…)` already interpolates
(`orchestrator.py:138-139`). Keep `HeuristicPlanner` single-shot (no feedback) —
the loop only engages for planners that accept feedback.

> Minimal-surface alternative: leave `run()`'s signature and add the loop only on
> the LLM path. Either is fine; the requirement is that **feedback actually flows
> back and the model gets another attempt** — which it currently never does.

### 3c. Config / dependency

- Add `anthropic` to a `spike/requirements.txt` (root has none today).
- `make_call_model()` is only constructed when a key is present; `orchestrator.py`
  stays runnable with zero deps via the heuristic path (preserves the "runs
  without any API key" property the docs advertise).

---

## 4. The eval harness — `spike/eval_planner.py` (new)

The point of the gap: *measure* whether NL→plan actually works, instead of
asserting it on 4 hand-picked specs.

**Corpus (`spike/evals/specs.yaml`, ~15-20 cases).** Each: a natural-language
spec + the expected outcome. Cover:
- in-catalog happy paths ("log temperature to memory over I2C" → temp+eeprom)
- quantities ("two EEPROMs", "three EEPROMs") → distinct auto-addresses
- capacity rejection ("nine EEPROMs") → gated
- **out-of-catalog asks** ("add a CAN transceiver") → model must NOT invent;
  expected = either a graceful "unsupported" or a plan that omits it (never a
  hallucinated part — the enum makes naming one impossible, so assert the emitted
  ids ⊆ catalog)
- paraphrase robustness (same intent, different wording) → same block set

```yaml
- spec: "A microcontroller that logs temperature readings to memory over I2C"
  expect_pass: true
  must_include_tags: [temperature, eeprom]
- spec: "An MCU with nine EEPROM memory chips on one I2C bus"
  expect_pass: false
  expect_reason: address               # gate must reject (capacity)
- spec: "An MCU that also needs a CAN bus transceiver"
  expect_pass: true                    # builds the I2C core; CAN absent
  forbid_outside_catalog: true         # emitted ids ⊆ catalog ids
```

**Metrics reported:**
- `plan_correctness` — fraction where verdict matches `expect_pass` AND any
  `must_include_tags` are present.
- `hallucination_rate` — must be **0** (every emitted `block_id` ∈ catalog). This
  is the headline safety number.
- `gate_catch_rate` — of specs expected to fail, fraction the gate rejected.
- attempts-to-pass distribution (does the retry loop help?).

**Runner:** `python3 eval_planner.py [--live]`. Default runs against the **fake
model** (§5); `--live` constructs `make_call_model()` and hits the API. Prints a
table + a single PASS/FAIL (fails if `hallucination_rate > 0` or
`plan_correctness` below a threshold, e.g. 0.85).

---

## 5. Testing without an API key (and CI)

The environment has no usable key, and CI won't either — so the LLM seam must be
testable deterministically.

**`FakeModel` (in `eval_planner.py` or a `tests/` helper):** a `call_model`-shaped
callable that parses the spec with the *same* heuristic mapping and returns a
valid `emit_plan` payload — plus adversarial variants that try to (a) name a
part outside the enum and (b) emit an unsatisfiable plan, to prove the enum
rejects the former and the gate rejects the latter. This lets CI assert the two
safety layers **without a model**.

**CI (`/session-start-hook` + a workflow):** run, in order —
`seam_validator.py`, `block_contract.py --faults`, `orchestrator.py`,
`eval_planner.py` (fake model). All already exit non-zero on failure. This also
closes GAPS §5 item 4 (no CI today).

---

## 6. File-by-file change list

| File | Change |
|---|---|
| `spike/llm_client.py` | **new** — `make_call_model()` (§3a) |
| `spike/orchestrator.py` | edit `run()` for the real feedback→retry loop (§3b); inject `make_call_model()` in `__main__` when `ANTHROPIC_API_KEY` is set, else heuristic |
| `spike/eval_planner.py` | **new** — corpus runner + metrics + `FakeModel` (§4, §5) |
| `spike/evals/specs.yaml` | **new** — the eval corpus |
| `spike/requirements.txt` | **new** — `anthropic` (+ `pyyaml`, already used) |
| `.github/workflows/ci.yml` *(or SessionStart hook)* | **new** — run the four scripts (§5) |
| `ORCHESTRATOR.md` | correct the "retry loop is wired" claim once it actually is; add eval results |

---

## 7. Acceptance criteria

1. `python3 eval_planner.py` (fake model) exits 0 with `hallucination_rate == 0`.
2. `python3 eval_planner.py --live` (with a key) reports `plan_correctness ≥ 0.85`
   on the corpus and `hallucination_rate == 0`.
3. An out-of-catalog spec never yields a `block_id` outside the catalog (enum
   guarantee, asserted in the fake-model test).
4. A spec the model plans wrongly is **caught by the gate**, the feedback reaches
   the model, and at least one corpus case demonstrably passes on attempt ≥ 2.
5. `orchestrator.py` still runs end-to-end with no API key (heuristic path).
6. CI runs all four scripts green.

---

## 8. Risks & open decisions

- **Forced-tool vs. thinking.** v1 forces `emit_plan` with thinking off (simple
  catalog). Revisit if specs get complex — switch to adaptive thinking + auto
  tool choice and lean harder on the gate. *Decision needed only if v1 eval
  correctness is low on paraphrases.*
- **Catalog size.** With only 4 blocks (and no real MCU), the planner's job is
  trivial — a strong eval result here is necessary but not sufficient. This spec
  proves the *mechanism*; breadth (GAPS §5 item 2) proves it *scales*. Don't
  oversell a green eval on 4 blocks.
- **Cost/latency.** Each retry is a full request. Cap `max_attempts=3`; the gate
  feedback is small. Negligible at eval scale.
- **Determinism in CI.** The live eval is non-deterministic by nature; CI gates on
  the **fake-model** run. The live run is a manual/scheduled check, reported but
  not blocking.

> Builds directly on the existing seam in `orchestrator.py` and the gate in
> `seam_validator.py` / `electrical.py`. Closes GAPS §5 item 1 and (via CI) item 4.
