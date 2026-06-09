# Handoff — NL-Devices

You are a Claude instance picking up this repo cold. Read this first. It is the
single entry point: what the project is, where it stands, the landmines that cost
the last session real time, and how to operate here without breaking things.

---

## What this is

**NL → validated schematic/netlist + BOM → routed PCB → fab.** Natural language is
the interface; **validation is the product.** Anyone can ask an LLM for a circuit.
The moat is the gauntlet that proves the design is real before it reaches copper:
a seam-validator, a ground-truth part DB, real electrical sims, and an autorouter
that emits DRC-clean Gerbers or fails the build.

"Done" for any leg means **CI-gated, not demoed.** A green check that would go red
if the design regressed. If it isn't enforced in `.github/workflows/ci.yml`, it
isn't done.

---

## First five minutes (read in this order)

1. **`DESIGN.md`** — the thesis and the architecture. The BUILD/BUY/AVOID table is
   the spine of every scope decision.
2. **`GAPS.md`** — the skeptical self-audit. Honest distance to the goal, per pillar,
   with 🔴/🟡/🟢 status. This is where you find what's actually unfinished.
3. **`SPEC-ROUTING.md`** — the most recent feature (autoroute → copper → fab), the one
   that closed the last 🔴. Good model for how a leg gets specced before it's built.
4. **`context-network/discovery.md`** — navigation hub for the deeper map (foundation,
   per-subsystem architecture notes, numbered decision records, roadmap). **See the
   note under Current State: this network may not be committed yet.**
5. **`spike/README.md`** — the actual code. Everything runnable lives under `spike/`.

The other root docs (`SPEC-*.md`, `ORCHESTRATOR.md`, `RESEARCH.md`, `BUSINESS.md`,
`DECISION.md`, `SPIKE.md`) are reference depth — pull them when a task touches them.

---

## Operating constraints — read before you run anything

These are not preferences. Each one cost the previous session a wrong turn.

- **Do not run heavy compute locally. You will OOM the owner's box.** No local
  `pip install`, `ato build`, KiCad, freerouting, or test runs. **CI on GitHub
  runners is the test runner.** Author code locally, push, let CI execute. Railway
  is the other allowed offload target. Author here, run there.

- **The sandbox cannot download CI artifacts** (Azure blob is unreachable from here).
  So when a CI job produces a result you need to see (Gerbers, a built board, a
  report), the job **commits the result back** with a `[skip ci]` commit and
  `permissions: contents: write`. You then `git pull`. Don't try to fetch artifacts.

- **GitHub auth is `gh` as `benzsevern`.** Not the `github-pat` MCP, not
  `benzsevern-mjh`. Push over an embedded-token URL:
  `git push https://x-access-token:$(gh auth token)@github.com/benseverndev-oss/NL-Devices <branch>`.
  The repo is **public**.

- **Squash-merge breaks `git merge-base --is-ancestor`.** Squash-merged PR commits
  are never ancestors of trunk, so that check always says "unmerged" and lies. To
  tell if work landed: `git fetch` then compare trees / read `git log` on trunk.
  The last session opened a redundant no-op PR (#7) trusting `--is-ancestor`. Don't.

- **Commit only when asked, on a branch off trunk, then PR.** Trunk is
  `claude/brainstorm-idea-vegk59` (yes, that's the long-lived trunk for this repo).
  Merge to trunk only on green CI.

---

## Toolchain pins (all enforced by `scripts/check_toolchain.py` + CI)

| Tool | Version | Why pinned |
| --- | --- | --- |
| atopile | **0.12.5** | 0.13+ needs Python 3.14, which crashes. Hard pin. |
| Python (build) | **3.13** | atopile 0.12.5's requirement. |
| KiCad | **9.0** | `kicad-cli` DRC/Gerbers + `pcbnew` Specctra DSN/SES. |
| freerouting | **2.1.0** | The autorouter. **Needs Java 21** (class-file 65); default-jre 17 throws `UnsupportedClassVersionError`. |

KiCad 9 dropped `kicad-cli` Specctra export, so DSN/SES go through
`pcbnew.ExportSpecctraDSN` / `ImportSpecctraSES` under `/usr/bin/python3`
(`spike/scripts/kicad_specctra.py`). freerouting runs headless:
`java -Djava.awt.headless=true -jar freerouting.jar -de DSN -do SES -mp 100`, and you
read `"incomplete_count": N` from its output to count unrouted nets.

---

## Current state (2026-06-09)

- **Trunk tip `98424ef`** — PR #8, the autoroute pillar, merged. The pipeline
  (`ato build` → place → DSN → freerouting → SES → DRC → Gerbers → fab package) is a
  **hard CI gate**: `spike/route.py --pipeline` exits nonzero unless **0 unrouted nets
  and 0 DRC violations**, against the `verified` board (MCU-class, not the passive stub).

- **CI has three jobs** (`.github/workflows/ci.yml`): `spike` (validator + contract +
  orchestrator + planner eval + part-data gate + ngspice sims + fab export, all offline),
  `toolchain` (pinned atopile install), and `route` (the autoroute gate above).

- **The `context-network/` is created but may be uncommitted.** It is the shared
  "second brain" (foundation, architecture, decisions/0001–0005, roadmap, meta),
  mirroring the goldenmatch repo's methodology. **If you cloned this and
  `context-network/` is absent, it was never committed** — work from the root docs,
  which are the source of truth either way. The network only ever *points* at them.

---

## Running the autoroute gate (CI, not local)

It's wired as the `route` job. The load-bearing command:

```
python3 spike/route.py --pipeline \
  --board spike/atopile/elec/layout/verified/verified.kicad_pcb \
  --jar freerouting.jar \
  --specctra spike/scripts/kicad_specctra.py \
  --work spike/build/route
```

`ato build -b verified` is reproducible because the per-part 3D `.step` models are
committed (atopile needs them; they're un-gitignored on purpose, ~25MB). Only the LCSC
part-pick hits the network. Pure parsers in `route.py` and `place.py` have offline
`--selftest` modes that the `spike` job runs against committed fixtures — use those to
sanity-check parser changes without the full toolchain.

---

## What's next (by leverage — none blocking; see `context-network/planning/roadmap.md`)

1. **Prove the NL leg for real.** The orchestrator eval runs a `FakeModel`. Run it
   `--live` and record it. Until then the product's namesake is unproven.
2. **Wire the STM32 block into a build target** (MCU + LDO + EEPROM) for a fuller
   routed board. The block exists in the parts lib but no `App` composes it — an
   atopile design change, the natural next routing step.
3. **Two remaining validator false-negative checks:** `power-connectivity` (cheap) and
   `i2c-multimaster`. Plus wiring the proven decoupling-droop sim into the gate.
4. **Datasheet → structured-data extraction** — named BUILD IP in `DESIGN.md`, still 0.

Business assumptions (respin willingness-to-pay, fab wholesale margin) are the owner's
to test, not codeable — see `BUSINESS.md` / `GAPS.md` §8.

---

## How to work here

1. **Brainstorm → spec → plan → execute**, with spec and code review gates. Plans land
   in `docs/superpowers/plans/`. `SPEC-ROUTING.md` + `docs/superpowers/plans/2026-06-09-autoroute-copper.md`
   are the worked example.
2. **Branch off trunk, PR, merge on green.** Never push straight to trunk.
3. **CI is the proof.** A feature isn't done until a CI job would fail without it.
4. **When you finish a milestone**, update the relevant `context-network/` node + add an
   `context-network/meta/updates.md` line (if the network is committed), and keep
   `GAPS.md` honest.

---

**Owner:** Ben (`benzsevern`). **Repo:** `benseverndev-oss/NL-Devices` (public).
**Trunk:** `claude/brainstorm-idea-vegk59`. **Last verified:** 2026-06-09 against `98424ef`.
