# Phase 1 — Headless CLI & CI Mode

**Status: ✅ DONE**  
**Shipped in:** v0.1.x

---

## What exists

VoxArena already has a full headless CLI (`voxarena/cli.py`). This phase is complete.

```bash
# Run a single provider eval
voxarena run --provider gemini --script script/utterances.json --num-turns 10 --output results.json

# Side-by-side comparison
voxarena compare --providers gemini,openai --script script/utterances.json

# Threshold-based pass/fail for CI
voxarena run --provider gemini \
  --min-tool-accuracy 0.85 \
  --max-hallucinations 2 \
  --max-avg-ttfa-ms 2500

# JUnit XML output for CI test reporters
voxarena run --provider gemini --junit results.xml
```

### Commands

| Command | Description |
|---------|-------------|
| `voxarena run` | Single-provider eval with exit 0/1 based on thresholds |
| `voxarena compare` | Parallel Gemini vs OpenAI eval |
| `voxarena report` | Print summary of a past run from results DB |
| `voxarena ui` | Launch the browser UI |
| `voxarena config` | Show/set config (API keys, models) |

### CI features already working

- Exit code `0` = pass, `1` = threshold failure, `2` = runtime error
- `--output` writes structured JSON
- `--junit` writes JUnit XML (compatible with GitHub Actions test reporter)
- `--min-tool-accuracy`, `--max-hallucinations`, `--max-avg-ttfa-ms` threshold flags
- `direct-injection` transport works without audio hardware (default for headless)

---

## What's still missing (follow-on improvements)

- **`--template` flag** — currently uses `--script <path>`. Should accept a template ID from the DB (`voxarena run --provider gemini --template finance`) so headless mode aligns with the UI's template system.
- **GitHub Actions example** — a copy-paste `.github/workflows/voxarena.yml` in `examples/` would help adoption.
- **`voxarena doctor`** — diagnoses missing API keys, ffmpeg, DB state before the user hits a runtime error.
- **Env var config** — `GEMINI_API_KEY` / `OPENAI_API_KEY` env vars for CI environments where writing a config file isn't practical.
