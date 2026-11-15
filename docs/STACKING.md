# Stacked pull requests

Work lands as a stack of small PRs, each one a contiguous slice of a single linear history. Every PR's base is the PR below it, so a reviewer sees only that slice's diff.

## Current stack

Slices 1–9 (#2, #4–#10, #1) landed on `main` on 2026-11-15 with merge commits.

| order | PR | branch | slice |
|---|---|---|---|
| 10 | (this) | `claude/stack-10-crt-desk` | cream, deeper CRT; lavender desk; softer accent |

## Landing

1. Merge the bottom PR into `main` with a **merge commit** or a fast-forward.
2. GitHub retargets the next PR to `main` automatically. Its diff stays the same, because its branch already contains the merged commits.
3. Repeat, bottom to top.

**Do not squash or rebase-merge.** Either one gives `main` new SHAs, so every PR above it would need a rebase and could conflict.

## Adding a slice

- Branch from the current top of the stack, as `claude/stack-NN-<topic>`, and open its PR with the old top as its base.
- Keep a slice to one reviewable idea: about 150–600 changed lines, with its tests.
- If review asks for a change in a lower slice, commit the fix on that slice's branch. Then merge it upward through each branch above it, using `git merge`, not rebase, so no published SHA changes.
