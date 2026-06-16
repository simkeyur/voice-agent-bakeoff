# Phase 1 — Headless CLI & CI Mode

**Target version:** v0.2  
**Impact:** Unlocks the single biggest use case — running evals in a CI pipeline without a browser.

---

## Problem

Right now VoxArena requires a human watching the UI to start a run. This means:

- Can't run in GitHub Actions / CircleCI / Jenkins
- Can't gate a PR on eval regression
- Can't schedule nightly benchmarks
- The tool is invisible to teams that live in the terminal

## Goal

```bash
# Run an eval from the terminal, get structured output
voxarena run --template finance --provider gemini --turns 10 --output results.json

# Exit code 0 = pass, 1 = fail (based on thresholds)
voxarena run --template finance --min-accuracy 0.85 --max-ttfa 2500
```

---

## What to Build

### 1. `voxarena run` CLI command

Add a `run` subcommand to `voxarena.cli`:

```
voxarena run [OPTIONS]

Options:
  --template TEXT       Template ID or name to run  [required]
  --provider TEXT       gemini | openai  [default: gemini]
  --model TEXT          Model override (default: from config)
  --transport TEXT      direct-injection | webrtc-local  [default: direct-injection]
  --turns INT           Number of turns to run  [default: all]
  --output PATH         Write JSON results to this file
  --min-accuracy FLOAT  Fail if tool-call accuracy drops below threshold
  --max-ttfa INT        Fail if median TTFA exceeds threshold (ms)
  --quiet               Suppress progress output (just exit code)
```

### 2. Structured JSON output

```json
{
  "run_id": "run_1234_abcd",
  "provider": "gemini",
  "model": "gemini-3.1-flash-live-preview",
  "template": "finance",
  "started_at": "2026-06-15T23:00:00Z",
  "duration_ms": 18400,
  "summary": {
    "turns_total": 10,
    "turns_completed": 10,
    "tool_call_accuracy": 0.90,
    "hallucination_rate": 0.05,
    "ttfa_median_ms": 1820,
    "ttfa_p95_ms": 2340
  },
  "turns": [ ... ]
}
```

### 3. Exit codes for CI

| Code | Meaning |
|------|---------|
| 0 | All turns completed, all thresholds passed |
| 1 | One or more threshold checks failed |
| 2 | Run did not complete (timeout, API error) |

### 4. GitHub Actions example (ship in docs)

```yaml
- name: Run VoxArena eval
  run: |
    voxarena run \
      --template finance \
      --provider gemini \
      --min-accuracy 0.85 \
      --output eval-results.json

- name: Upload eval results
  uses: actions/upload-artifact@v4
  with:
    name: eval-results
    path: eval-results.json
```

---

## Implementation Notes

- The existing `POST /api/run` + polling loop already works; the CLI just needs to call it and block.
- `direct-injection` transport works without audio hardware — make it the default for headless mode.
- Progress output should go to stderr so stdout can be piped to `jq`.
- Config (API keys, model) should be readable from env vars (`GEMINI_API_KEY`, `OPENAI_API_KEY`) so no `voxarena.db` is needed in CI.

---

## Success Criteria

- `voxarena run --template finance --provider gemini` works from a fresh Docker container with only `GEMINI_API_KEY` set.
- Exit code is non-zero when accuracy drops below threshold.
- A GitHub Actions workflow in `examples/` demonstrates it end-to-end.
