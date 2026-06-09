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
QTY = {"two": 2, "2": 2, "dual": 2, "pair": 2, "double": 2,
       "three": 3, "3": 3, "triple": 3}


# ---- planner interface ------------------------------------------------------
class Planner:
    def plan(self, spec: str, lib: dict[str, bc.BlockSpec]) -> dict:
        raise NotImplementedError


def _pick_tag(lib, tag):
    for b in lib.values():
        if tag in b.tags:
            return b
    raise LookupError(f"no block in catalog provides '{tag}'")


def _build_slice(instances: dict[str, str]) -> dict:
    sensors = [k for k in instances if k.startswith("s")]
    return {
        "name": "generated",
        "instances": instances,
        "rails": [
            {"name": "5V", "source": {"voltage": 5.0, "tolerance": 0.05},
             "sinks": ["psu.power_in"]},
            {"name": "3V3", "source_from": "psu.power_out",
             "sinks": ["mcu.power"] + [f"{s}.power" for s in sensors]},
        ],
        "buses": [{"name": "i2c_bus", "type": "i2c",
                   "members": ["mcu.i2c"] + [f"{s}.i2c" for s in sensors]}],
    }


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
            qty = next((n for w, n in QTY.items() if w in s.split()), 1)
            cands = [b for b in lib.values() if cap in b.tags]
            # prefer distinct addresses; cycle if the spec asks for more than exist
            for i in range(qty):
                chosen.append(cands[i % len(cands)] if cands else None)
        for i, b in enumerate(c for c in chosen if c):
            instances[f"s{i}"] = b.id
        return _build_slice(instances)


# ---- LLM planner: the seam (constrained so it can't invent parts) -----------
class LLMPlanner(Planner):
    """How a real LLM plugs in. `call_model(system, user, tools)` is injected;
    with no client it raises — this prototype runs the heuristic planner."""

    def __init__(self, call_model=None):
        self.call_model = call_model

    def catalog(self, lib) -> str:
        lines = []
        for b in lib.values():
            addr = b.ports.get("i2c", {}).get("address")
            part = b.bound_part["lcsc"] if b.bound_part else "abstract"
            lines.append(f"- {b.id}: {b.function} | tags={b.tags} | part={part}"
                         + (f" | i2c_addr=0x{addr:02X}" if addr is not None else ""))
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
        return _build_slice(instances)


# ---- pipeline: plan -> validate (the gate) ----------------------------------
def run(spec, lib, planner: Planner):
    plan = planner.plan(spec, lib)
    design = bc.build_design(plan, lib)
    res = sv.validate(design)
    ok = not any(res.values())
    return plan, design, res, ok


def _render(plan, lib):
    out = []
    for inst, bid in plan["instances"].items():
        b = lib[bid]
        addr = b.ports.get("i2c", {}).get("address")
        part = b.bound_part["lcsc"] if b.bound_part else "abstract"
        out.append(f"      {inst:<6} = {bid:<26} [{part}"
                   + (f", 0x{addr:02X}" if addr is not None else "") + "]")
    return "\n".join(out)


if __name__ == "__main__":
    lib = bc.load_blocks()
    planner = HeuristicPlanner()
    print(f"Verified-block catalog ({len(lib)} blocks): {', '.join(lib)}\n")

    specs = [
        "A microcontroller that logs temperature readings to memory over I2C",
        "An I2C node: an MCU with two EEPROM memory chips",
        "An MCU with three EEPROM memory chips on one I2C bus",   # exceeds distinct addrs -> GATED
    ]
    all_expected = True
    for spec in specs:
        plan, design, res, ok = run(spec, lib, planner)
        print(f"SPEC: {spec}")
        print(_render(plan, lib))
        print(f"   -> VALIDATION: {'PASS — design accepted' if ok else 'REJECTED by gate'}")
        for msgs in res.values():
            for m in msgs:
                print(f"        └─ {m}")
        # the 3rd spec is expected to be gated (only 2 distinct EEPROM addresses)
        expect_ok = "three" not in spec.lower()
        all_expected &= (ok == expect_ok)
        # --build: take passing designs all the way to a manufacturable BOM
        if ok and "--build" in sys.argv:
            import codegen
            built, bom = codegen.build(plan, lib, target=f"gen_{specs.index(spec)}")
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
