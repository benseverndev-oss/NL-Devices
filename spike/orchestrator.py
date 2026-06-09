"""NL -> validated design orchestrator (prototype).

Closes the loop the whole project is about: a natural-language spec becomes a
design by COMPOSING pre-verified blocks (never synthesising parts), and the
deterministic seam-validator GATES the result. The LLM is one pluggable planner;
its only job is to pick + wire blocks from the closed catalog, so it cannot
hallucinate parts — and whatever it emits must still pass validation.

  spec ──► Planner ──► slice (instances+rails+buses) ──► validate ──► PASS/REJECT
            ▲ pluggable: HeuristicPlanner (now) | LLMPlanner (seam, enum-constrained)

Run:  python3 orchestrator.py
"""
from __future__ import annotations
import inspect
import json
import sys
from pathlib import Path

import block_contract as bc
import seam_validator as sv

HERE = Path(__file__).parent

# capability keyword -> block tag
CAPS = {
    "temperature": ["temperature", "temp", "thermal", "thermometer", "climate"],
    "eeprom":      ["eeprom", "memory", "storage", "store", "log", "logger",
                    "logging", "record", "data"],
}
QTY = {"two": 2, "dual": 2, "pair": 2, "double": 2, "three": 3, "triple": 3,
       "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _qty(spec: str) -> int:
    for t in spec.lower().replace(",", " ").split():
        if t in QTY:
            return QTY[t]
        if t.isdigit():
            return int(t)
    return 1


# ---- planner interface ------------------------------------------------------
class Planner:
    def plan(self, spec: str, lib: dict[str, bc.BlockSpec]) -> dict:
        raise NotImplementedError


def _pick_tag(lib, tag):
    for b in lib.values():
        if tag in b.tags:
            return b
    raise LookupError(f"no block in catalog provides '{tag}'")


def _build_slice(instances: dict[str, str], lib: dict[str, bc.BlockSpec]) -> dict:
    """Compose instances into a validatable slice, classifying each instance by
    its catalog block's ROLE (not by instance-name convention) — so a planner may
    name instances anything. Power block drives the 3V3 rail; the I2C controller
    and every I2C peripheral join the bus."""
    def has_tag(bid, tag):
        return bid in lib and tag in lib[bid].tags

    def i2c_role(bid):
        return lib[bid].ports.get("i2c", {}).get("role") if bid in lib else None

    psu = next((k for k, b in instances.items() if has_tag(b, "power")), None)
    mcu = next((k for k, b in instances.items() if has_tag(b, "controller")), None)
    sensors = [k for k, b in instances.items() if i2c_role(b) == "peripheral"]

    rails, buses = [], []
    if psu:
        rail3_sinks = ([f"{mcu}.power"] if mcu else []) + [f"{s}.power" for s in sensors]
        rails = [
            {"name": "5V", "source": {"voltage": 5.0, "tolerance": 0.05},
             "sinks": [f"{psu}.power_in"]},
            {"name": "3V3", "source_from": f"{psu}.power_out", "sinks": rail3_sinks},
        ]
    bus_members = ([f"{mcu}.i2c"] if mcu else []) + [f"{s}.i2c" for s in sensors]
    if bus_members:
        buses = [{"name": "i2c_bus", "type": "i2c", "members": bus_members}]
    return {"name": "generated", "instances": instances, "rails": rails, "buses": buses}


class HeuristicPlanner(Planner):
    """Deterministic stand-in: maps capability keywords to catalog blocks."""

    def plan(self, spec, lib):
        s = spec.lower()
        instances = {"psu": _pick_tag(lib, "power").id,
                     "mcu": _pick_tag(lib, "controller").id}
        chosen = []
        for cap, kws in CAPS.items():
            if not any(k in s for k in kws):
                continue
            qty = _qty(spec)
            cands = [b for b in lib.values() if cap in b.tags]
            # prefer distinct addresses; cycle if the spec asks for more than exist
            for i in range(qty):
                chosen.append(cands[i % len(cands)] if cands else None)
        for i, b in enumerate(c for c in chosen if c):
            instances[f"s{i}"] = b.id
        return _build_slice(instances, lib)


# ---- LLM planner: the seam (constrained so it can't invent parts) -----------
class LLMPlanner(Planner):
    """How a real LLM plugs in. `call_model(system, user, tools)` is injected;
    with no client it raises — this prototype runs the heuristic planner."""

    def __init__(self, call_model=None):
        self.call_model = call_model

    def catalog(self, lib) -> str:
        lines = []
        for b in lib.values():
            base = b.ports.get("i2c", {}).get("address_base")
            part = b.bound_part["lcsc"] if b.bound_part else "abstract"
            lines.append(f"- {b.id}: {b.function} | tags={b.tags} | part={part}"
                         + (f" | i2c_base=0x{base:02X}" if base is not None else ""))
        return "\n".join(lines)

    def tool_schema(self, lib) -> dict:
        # block_id is an ENUM of catalog ids -> the model literally cannot name a
        # part outside the verified library. This is the anti-hallucination guard.
        return {
            "name": "emit_plan",
            "description": "Compose a device by selecting and naming verified blocks.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "instances": {
                        "type": "array",
                        "items": {"type": "object", "properties": {
                            "name": {"type": "string"},
                            "block_id": {"type": "string", "enum": list(lib)},
                        }, "required": ["name", "block_id"]},
                    },
                },
                "required": ["instances"],
            },
        }

    def messages(self, spec, lib, feedback=None):
        system = ("You are a hardware design planner. Compose the requested device "
                  "by SELECTING blocks from the VERIFIED BLOCK CATALOG. You may only "
                  "use block_ids from the catalog — never invent parts. Always include "
                  "a power block and a controller. Call emit_plan.\n\nCATALOG:\n"
                  + self.catalog(lib))
        user = f"Device request: {spec}"
        if feedback:
            user += f"\n\nThe previous plan FAILED validation:\n{feedback}\nFix it."
        return system, user

    def plan(self, spec, lib, feedback=None):
        if not self.call_model:
            raise RuntimeError("LLMPlanner has no model client — this is the seam. "
                               "Inject call_model(system, user, tools) to enable.")
        system, user = self.messages(spec, lib, feedback)
        raw = self.call_model(system, user, [self.tool_schema(lib)])
        instances = {i["name"]: i["block_id"] for i in raw["instances"]}
        return _build_slice(instances, lib)


# ---- pipeline: plan -> validate (the gate), with feedback retry --------------
def _accepts_feedback(planner: Planner) -> bool:
    try:
        return "feedback" in inspect.signature(planner.plan).parameters
    except (ValueError, TypeError):
        return False


def _format_feedback(res: dict[str, list[str]]) -> str:
    return "\n".join(f"- [{check}] {m}" for check, msgs in res.items() for m in msgs)


def run(spec, lib, planner: Planner, *, max_attempts: int = 3):
    """Plan -> gate, looping on validator feedback for planners that accept it.

    The gate (topology + I2C addressing + electrical) owns correctness; a planner
    is never trusted. For a feedback-aware planner (the LLM seam), a rejected plan
    is fed back and re-attempted up to `max_attempts`. Returns the last attempt's
    (plan, design, res, ok, attempts). `design` is None if a plan couldn't even be
    assembled (e.g. the planner named an out-of-catalog part) — itself a rejection."""
    import electrical
    uses_feedback = _accepts_feedback(planner)
    feedback = None
    plan, design, res, ok, attempt = {"instances": {}}, None, {}, False, 0
    for attempt in range(1, max_attempts + 1):
        try:
            plan = planner.plan(spec, lib, feedback) if uses_feedback else planner.plan(spec, lib)
            design = bc.build_design(plan, lib)
            res = sv.validate(design)                                  # topology seams
            res["electrical"] = electrical.check_electrical(plan, lib)  # ngspice gate
        except Exception as e:                       # malformed/hallucinated plan -> reject
            design, res = None, {"assembly": [f"plan could not be assembled: {e}"]}
        ok = design is not None and not any(res.values())
        if ok or not uses_feedback:
            break
        feedback = _format_feedback(res)
    return plan, design, res, ok, attempt


def _render(plan, lib, design=None):
    addr = ({n.block: n.address for bus in design.buses for n in bus.nodes
             if n.role == "peripheral"} if design else {})
    out = []
    for inst, bid in plan["instances"].items():
        b = lib[bid]
        part = b.bound_part["lcsc"] if b.bound_part else "abstract"
        a = addr.get(inst)
        out.append(f"      {inst:<6} = {bid:<26} [{part}"
                   + (f", 0x{a:02X}" if a is not None else "") + "]")
    return "\n".join(out)


if __name__ == "__main__":
    import os
    lib = bc.load_blocks()
    # Use a real Claude planner when a key is present; else the deterministic
    # heuristic (keeps this runnable — and CI-deterministic — with no API key).
    if os.environ.get("ANTHROPIC_API_KEY"):
        from llm_client import make_call_model
        planner = LLMPlanner(make_call_model())
        print("Planner: LLMPlanner (claude-opus-4-8)")
    else:
        planner = HeuristicPlanner()
        print("Planner: HeuristicPlanner (no ANTHROPIC_API_KEY — LLM seam idle)")
    print(f"Verified-block catalog ({len(lib)} blocks): {', '.join(lib)}\n")

    specs = [
        # (spec, expect_pass)
        ("A microcontroller that logs temperature readings to memory over I2C", True),
        ("An I2C node: an MCU with two EEPROM memory chips", True),
        ("An MCU with three EEPROM memory chips on one I2C bus", True),   # auto-addressed 0x50/0x51/0x52
        ("An MCU with nine EEPROM memory chips on one I2C bus", False),   # exhausts 0x50..0x57 -> GATED
    ]
    all_expected = True
    for i, (spec, expect_ok) in enumerate(specs):
        plan, design, res, ok, attempts = run(spec, lib, planner)
        print(f"SPEC: {spec}")
        print(_render(plan, lib, design))
        verdict = "PASS — design accepted" if ok else "REJECTED by gate"
        print(f"   -> VALIDATION: {verdict}" + (f" (attempts: {attempts})" if attempts > 1 else ""))
        for msgs in res.values():
            for m in msgs:
                print(f"        └─ {m}")
        all_expected &= (ok == expect_ok)
        # --build: take passing designs all the way to a manufacturable BOM
        if ok and "--build" in sys.argv:
            import codegen
            built, bom = codegen.build(plan, lib, target=f"gen_{i}")
            print(f"   -> CODEGEN+BUILD: {'manufacturable BOM' if built else 'build failed'}")
            if built:
                for line in bom.strip().splitlines()[1:]:
                    print(f"        {line}")
        print()

    print("=" * 68)
    print("LLM SEAM (how a model plugs in — constrained to the catalog):")
    seam = LLMPlanner()
    print("  emit_plan tool — block_id enum (cannot name a part outside the library):")
    print("   ", json.dumps(seam.tool_schema(lib)["input_schema"]["properties"]
                            ["instances"]["items"]["properties"]["block_id"]))
    print("\nRESULT:", "PASS — composed + gated as expected" if all_expected else "FAIL")
    raise SystemExit(0 if all_expected else 1)
