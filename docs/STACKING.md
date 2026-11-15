# Stacked pull requests

Work lands as a stack of small PRs, each one a contiguous slice of a single linear history. Every PR's base is the PR below it, so a reviewer sees only that slice's diff.

## Current stack

| order | PR | branch | slice |
|---|---|---|---|
| 1 | #2 | `claude/stack-01-toolkit` | toolkit |
| 2 | #4 | `claude/stack-02-v2-design` | v2 design docs |
| 3 | #5 | `claude/stack-03-review-fixes` | review fixes |
| 4 | #6 | `claude/stack-04-loop-audio` | loop drivers + audio stems |
| 5 | #7 | `claude/stack-05-screensaver` | screensaver |
| 6 | #8 | `claude/stack-06-look-match` | look-match + review round 2 |
| 7 | #9 | `claude/stack-07-autoresearch` | autoresearch harness |
| 8 | #10 | `claude/stack-08-rebuild-space` | framing, pier, passage, alcoves |
| 9 | #1 | `claude/lucid-goldberg-aw6nc3` | deeper room, water, tone, sweep |

## Landing

1. Merge the bottom PR into `main` with a **merge commit** or a fast-forward.
2. GitHub retargets the next PR to `main` automatically. Its diff stays the same, because its branch already contains the merged commits.
3. Repeat, bottom to top.

**Do not squash or rebase-merge.** Either one gives `main` new SHAs, so every PR above it would need a rebase and could conflict.

## Adding a slice

- Branch from the current top of the stack, as `claude/stack-NN-<topic>`, and open its PR with the old top as its base.
- Keep a slice to one reviewable idea: about 150–600 changed lines, with its tests.
- If review asks for a change in a lower slice, commit the fix on that slice's branch. Then merge it upward through each branch above it, using `git merge`, not rebase, so no published SHA changes.
