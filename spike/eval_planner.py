"""Eval harness for the NL planner (SPEC-NL-PLANNER.md §4-5).

Runs a corpus of natural-language specs through the LLMPlanner + the deterministic
gate and reports plan-correctness, a 0-hallucination safety number, and the
gate-catch rate. Default uses an offline FakeModel so the safety contract is
testable in CI without an API key; `--live` hits a real claude-opus-4-8.

Run:  python3 eval_planner.py            # offline (FakeModel)
      python3 eval_planner.py --live     # real model (needs ANTHROPIC_API_KEY)
"""
from __future__ import annotations
import sys
from pathlib import Path

import yaml

import block_contract as bc
import orchestrator as orch

HERE = Path(__file__).parent
CORRECTNESS_THRESHOLD = 0.85


# ---- offline fake model: a deterministic, catalog-respecting call_model ------
class FakeModel:
    """A `call_model`-shaped stand-in for CI. It mirrors the heuristic capability
    mapping and emits the SAME emit_plan payload shape a real model would. In
    `mode="hallucinate"` it deliberately names a part OUTSIDE the catalog — used to
    prove the pipeline (layer 2) rejects what the API's enum (layer 1) would block."""

    def __init__(self, lib: dict[str, bc.BlockSpec], mode: str = "honest"):
        self.lib, self.mode = lib, mode

    def __call__(self, system: str, user: str, tools: list[dict]) -> dict:
        s = user.lower()
        power = next(b for b in self.lib.values() if "power" in b.tags)
        ctrl = next(b for b in self.lib.values() if "controller" in b.tags)
        insts = [{"name": "psu", "block_id": power.id},
                 {"name": "mcu", "block_id": ctrl.id}]
        idx = 0
        for cap, kws in orch.CAPS.items():
            if not any(k in s for k in kws):
                continue
            cands = [b for b in self.lib.values() if cap in b.tags]
            if not cands:
                continue
            for i in range(orch._qty(user)):
                insts.append({"name": f"s{idx}", "block_id": cands[i % len(cands)].id})
                idx += 1
        if self.mode == "hallucinate":
            insts.append({"name": "bad", "block_id": "sensor_can_mcp2515_NOTREAL"})
        return {"instances": insts}


# ---- scoring -----------------------------------------------------------------
def _selected_tags(plan, lib):
    tags = set()
    for bid in plan["instances"].values():
        if bid in lib:
            tags.update(lib[bid].tags)
    return tags


def _outside_catalog(plan, lib):
    return [b for b in plan["instances"].values() if b not in lib]


def _failing_checks(res):
    return [k for k, v in res.items() if v]


def score_case(case, plan, res, ok, lib):
    """Return (correct: bool, hallucinated: bool, notes: str)."""
    hallucinated = bool(_outside_catalog(plan, lib))
    if ok != case["expect_pass"]:
        return False, hallucinated, f"verdict {ok} != expected {case['expect_pass']}"
    if case.get("forbid_outside_catalog") and hallucinated:
        return False, True, f"named non-catalog parts: {_outside_catalog(plan, lib)}"
    if ok:
        missing = set(case.get("must_include_tags", [])) - _selected_tags(plan, lib)
        if missing:
            return False, hallucinated, f"missing required tags: {sorted(missing)}"
    else:
        reason = case.get("expect_reason")
        if reason and not any(reason in c for c in _failing_checks(res)):
            return False, hallucinated, f"rejected for {_failing_checks(res)}, expected '{reason}'"
    return True, hallucinated, "ok"


# ---- runner ------------------------------------------------------------------
def run_eval(planner, lib, corpus):
    rows, correct, hallucinated, expect_fail, caught, attempts_hist = [], 0, 0, 0, 0, []
    for case in corpus:
        plan, design, res, ok, attempts = orch.run(case["spec"], lib, planner)
        good, halluc, note = score_case(case, plan, res, ok, lib)
        correct += good
        hallucinated += halluc
        attempts_hist.append(attempts)
        if not case["expect_pass"]:
            expect_fail += 1
            caught += (not ok)
        rows.append((case["spec"], ok, attempts, good, note))
    n = len(corpus)
    return {
        "rows": rows,
        "plan_correctness": correct / n,
        "hallucination_rate": hallucinated / n,
        "gate_catch_rate": (caught / expect_fail) if expect_fail else 1.0,
        "max_attempts": max(attempts_hist),
    }


def safety_check(lib):
    """Layer-2 proof: a planner that names a non-catalog part is REJECTED by the
    pipeline (not silently built). Independent of any model/enum enforcement."""
    bad_planner = orch.LLMPlanner(FakeModel(lib, mode="hallucinate"))
    plan, design, res, ok, _ = orch.run("log temperature to memory", lib, bad_planner,
                                        max_attempts=1)
    rejected = not ok
    enum_present = "enum" in str(bad_planner.tool_schema(lib))  # layer-1 contract declared
    return rejected and enum_present


class _SelfCorrectingModel:
    """First attempt over-fills the address space (rejected); on feedback it drops
    back to a valid plan. Proves the feedback->retry loop actually changes the
    outcome — recovery on attempt >= 2 (SPEC acceptance #4), deterministically."""

    def __init__(self, lib):
        self.lib, self.calls = lib, 0

    def __call__(self, system, user, tools):
        self.calls += 1
        eeprom = next(b for b in self.lib.values() if "eeprom" in b.tags)
        power = next(b for b in self.lib.values() if "power" in b.tags)
        ctrl = next(b for b in self.lib.values() if "controller" in b.tags)
        insts = [{"name": "psu", "block_id": power.id}, {"name": "mcu", "block_id": ctrl.id}]
        n = 9 if self.calls == 1 else 2          # over-capacity first, valid after feedback
        insts += [{"name": f"s{i}", "block_id": eeprom.id} for i in range(n)]
        return {"instances": insts}


def retry_check(lib):
    """Recovery on attempt >= 2: a self-correcting planner is rejected once, gets
    the gate feedback, and passes on retry."""
    planner = orch.LLMPlanner(_SelfCorrectingModel(lib))
    plan, design, res, ok, attempts = orch.run("an MCU with EEPROMs", lib, planner)
    return ok and attempts >= 2


def main(live: bool):
    lib = bc.load_blocks()
    corpus = yaml.safe_load((HERE / "evals" / "specs.yaml").read_text())

    if live:
        from llm_client import make_call_model
        planner = orch.LLMPlanner(make_call_model())
        print("Model: claude-opus-4-8 (live)\n")
    else:
        planner = orch.LLMPlanner(FakeModel(lib))
        print("Model: FakeModel (offline — deterministic, catalog-respecting)\n")

    m = run_eval(planner, lib, corpus)
    print(f"{'verdict':<8}{'att':<5}{'ok?':<5}spec")
    print("-" * 78)
    for spec, ok, attempts, good, note in m["rows"]:
        mark = "PASS" if ok else "REJECT"
        flag = "✓" if good else "✗"
        line = f"{mark:<8}{attempts:<5}{flag:<5}{spec[:48]}"
        print(line + ("" if good else f"   <- {note}"))
    print("-" * 78)
    print(f"plan_correctness   : {m['plan_correctness']:.2%}  (threshold {CORRECTNESS_THRESHOLD:.0%})")
    print(f"hallucination_rate : {m['hallucination_rate']:.2%}  (must be 0%)")
    print(f"gate_catch_rate    : {m['gate_catch_rate']:.2%}")
    print(f"max attempts used  : {m['max_attempts']}")

    safe = safety_check(lib)
    print(f"safety (layer-2)   : {'PASS' if safe else 'FAIL'} — out-of-catalog plan rejected by pipeline")
    recov = retry_check(lib)
    print(f"retry (recovery)   : {'PASS' if recov else 'FAIL'} — rejected plan fixed on attempt >= 2 via gate feedback")

    ok = (m["hallucination_rate"] == 0.0
          and m["plan_correctness"] >= CORRECTNESS_THRESHOLD
          and safe and recov)
    print("\nRESULT:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main(live="--live" in sys.argv)
