# Launch prompt

Paste this into a fresh Claude Code session opened at the repo root. On your RTX 4070 box, add `--device GPU` to the eval command for roughly 10x faster iterations.

---

Read `autoresearch/instructions.md` in full, then read the target preset (`wavegen/presets/poolrooms.json`) and the `DEFAULTS` in `wavegen/config.py` it merges onto.

1. Confirm the baseline. Run `.venv/bin/python autoresearch/eval.py --target poolrooms` once and check that SCORE matches the `baseline` in the config line of `autoresearch/autoresearch.jsonl`, within 0.001. If it doesn't, stop and report.
2. Run the loop for **30 iterations** exactly as the instructions say: one change per iteration, guards, keep or discard, a JSONL line, and a dashboard update.
3. Commit each kept change on the current branch. Do not push.
4. When done, or once the plateau rule triggers, write `autoresearch/report.md`.

If you are resuming after lost context, read `autoresearch/autoresearch.jsonl` and `autoresearch/autoresearch_dashboard.md` first, and continue from the last iteration.

---

## Other poolscape scenes

1. Put 3–5 reference frames in `docs/ref/<scene>/`.
2. Add a target to `autoresearch/targets.json`: `{"preset": "wavegen/presets/<scene>.json", "refs": [...], "frame": 1}`. Start the preset as a copy of the best poolrooms preset, so the learnings carry over.
3. Run the same loop with `--target <scene>`, using a fresh `autoresearch_<scene>.jsonl` and dashboard.
