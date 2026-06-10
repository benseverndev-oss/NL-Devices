# Network Maintenance

## Principles
- **Point, don't copy.** Thesis/architecture/strategy live in the root design docs
  (`DESIGN.md`, `GAPS.md`, `SPEC-*.md`); implementation lives in `docs/superpowers/plans/`.
  Nodes here link to those, not duplicate them. When they conflict, the source-of-truth
  wins and the node is wrong — fix the node.
- **Small, focused nodes.** One concern per file. If a node grows past ~1 screen, split it.
- **Cross-link liberally.** Every node should be reachable from
  [../discovery.md](../discovery.md) and link to its neighbors.
- **Classification footer** on every node: `domain/stability` + last-updated date.

## When to update
- After a workstream milestone (a PR that changes status/decisions): update the relevant
  architecture/decision node + add an [updates.md](updates.md) entry.
- When a decision is made with no code home (a trade-off, a "why we didn't"): add a numbered
  record under `../decisions/`.
- When the foundation changes (new subsystem, structural move): update `../foundation/`.

## What does NOT belong here
- Secrets / tokens (gitignored elsewhere).
- Transient task state or one-session scratch notes (use TodoWrite / user memory).
- Duplicates of the root design-doc detail.

## Committing
The network is meant to be committed (shared brain), but per the repo cadence commit only
when the user asks, on a branch off trunk. It is not in `.gitignore`; confirm before
`git add`.

---
**Classification:** meta/process • **Last updated:** 2026-06-09
