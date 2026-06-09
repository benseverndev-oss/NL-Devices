# Development Workflow

## The cadence
**spec → plan → execute → CI green → merge.** Each closed gap gets a root `SPEC-*.md` and
an implementation plan under `docs/superpowers/plans/`. Branch off trunk
(`claude/brainstorm-idea-vegk59`), get CI green, then
`gh pr merge <n> --squash --delete-branch`. Squash-merging one PR can conflict the next
branch on shared files (`ci.yml`, `GAPS.md`) — resolve by merging trunk in.

## Hard environment constraints (these shaped half the engineering)
- **No heavy compute on the maintainer's Windows box** — it OOMs; ngspice / atopile /
  KiCad / freerouting aren't installed there anyway. **Author locally (edits/reads only);
  CI on ubuntu is the test runner.** Push → watch CI → iterate.
- **The dev sandbox can't download GitHub artifacts** (Azure blob
  `productionresultssa3.blob.core.windows.net` is unreachable); git push/pull over
  github.com works. To get a CI-produced file into the repo, have CI **commit it back** to
  the branch with `[skip ci]` + `permissions: contents: write`, then `git pull`. (Used to
  land the 3D models + board fixture.)
- **`gh` account reverts between shells** — run `gh auth switch --user benzsevern` at the
  start of every `gh`/push command; push via embedded-token URL
  (`https://x-access-token:$(gh auth token)@github.com/...`). See
  [[github-account-for-nl-devices]] in user memory.
- **Verify merge state by fetching + comparing trees, NOT
  `git merge-base --is-ancestor <pre-squash-sha>`** — squash-merges make that test ALWAYS
  false; it once caused a redundant empty no-op merge.
- The repo is **public** so Actions are free/unmetered (a private-repo minute cap once
  silently stopped CI from creating runs — valid YAML + Actions "operational" + zero runs
  is the signature).

## CI (`.github/workflows/ci.yml`) — 3 jobs
- `spike` (offline, fast): pin lint + ngspice + every spike `--selftest`.
- `toolchain`: live `setup.sh` proves atopile 0.12.5 installs.
- `route`: KiCad 9 + Java 21 + freerouting + `ato build -b verified` + the full autoroute
  pipeline, hard-gated ([../architecture/autoroute-pipeline.md](../architecture/autoroute-pipeline.md)).

## Tests
The project uses `--selftest` self-asserting scripts gated in CI, **not pytest**. Match
that convention. Pure logic (placement, parsers, validation) is offline-testable; tool
invocations only run in the `route` job.

---
**Classification:** process/active • **Last updated:** 2026-06-09
