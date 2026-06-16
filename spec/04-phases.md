# Phased Plan

## Delivered (Phases 0-6)

The original phased plan below has been implemented and extended beyond its
initial scope. Summary of what exists today:

- **Contracts**: shared `ProviderConfig`, `RunManifest`/`TurnMetric`/
  `AggregateMetrics` models (`voxarena/manifest.py`), SQLite persistence
  (`voxarena/database.py`) alongside per-run JSON manifests.
- **Core agent**: provider-neutral `Agent` model, tool schemas, deterministic
  fake data, and a multi-template system (`voxarena/templates.py`) so the
  same harness can run different usecases (not just the restaurant scenario).
- **Provider adapters**: `voxarena/providers/` contains thin adapters for
  Gemini Live and OpenAI Realtime behind a shared `BaseProviderAdapter` /
  `RunMetricsCollector` (`voxarena/providers/base.py`).
- **Harness**: `voxarena/harness.py` drives a Pipecat pipeline — WAV
  injection (`AudioInjectionProcessor`), response capture
  (`AudioCaptureProcessor`), transport-level timestamps, late-frame handling
  for OpenAI's out-of-order tool-call frames, and per-turn audio caching
  (`voxarena/audio_cache.py`).
- **Script and evaluation**: `script/utterances.yaml` plus an in-app
  utterance editor backed by SQLite; `expect` checks scored per turn.
- **Reporting and UI**: a full dashboard/comparison UI (`ui/`) with run
  history, filtering/sorting, side-by-side comparison, confirmation modals,
  and metric showdown cards.

Everything below this point is **new work**, not yet delivered.

## Phase 7 - Scenario & Metric Extensibility

Goal: make `expect` checks and turn-execution behaviors additive — new
scenario types are new registry entries, not new branches in the harness or
evaluator.

Deliverables:

- **Turn-behavior registry** (`voxarena/turn_behaviors.py`): `_drive_turns`
  in `voxarena/harness.py` dispatches each turn to a handler keyed by the
  *next* turn's `behavior.type` (default `"sequential"`). Adding a new
  execution strategy (e.g. silence timeout, DTMF) is a new handler + registry
  entry.
- **Expect-check registry** (`voxarena/evaluators.py`): `evaluate_turn()`
  runs every checker in `EXPECT_CHECKS` whose key is present in the turn's
  `expect` block (plus `"tool"`, which always runs). Adding a new assertion
  type is a new checker function + registry entry.
- **Barge-in scenario**: a `behavior: {"type": "barge_in", "delay_ms": ...}`
  on a turn starts that turn's audio injection while the *previous* turn is
  still speaking, exercising `interruption_sent_at` /
  `interruption_stopped_at` / `interruption_stop_latency_ms` end-to-end
  (previously always `null` because the harness was strictly sequential).
  The previous turn can assert `expect.interrupted: true` via the new
  `check_interrupted` checker. Retrofitted onto the existing u06/u07 pair in
  `script/utterances.yaml`.
- **Cost tracking**: Pipecat's usage-metrics frames are enabled
  (`PipelineParams(enable_metrics=True, enable_usage_metrics=True)`), and
  `RunMetricsCollector` captures `prompt_tokens`/`completion_tokens` per turn
  from `LLMUsageMetricsData`. `voxarena/pricing.py` applies a flat per-model
  $/token table to populate `TurnMetric.cost_usd` and
  `AggregateMetrics.total_cost_usd` (previously always `0.0`).

Exit criteria:

- A new `expect` key or `behavior` type can be added without modifying
  `_drive_turns` or `evaluate_turn`'s control flow.
- `interruption_stop_latency_ms` and `total_cost_usd` are populated by at
  least one scenario, for both providers.

## Phase 8 (Future, not built) - Transcript Fidelity

Goal: score `transcript_output` against expected facts using an LLM judge,
populating `AggregateMetrics.transcript_fidelity_score` (currently always
`null`).

Sketch: a post-evaluation async hook (registered similarly to the Phase 7
registries) that sends the turn's transcript plus its `expect`/scenario
context to a judge model and returns a 0-1 score. This is deferred until the
registries from Phase 7 exist, since the hook should be additive rather than
another branch in `evaluate_turn`.

## Milestones

- M1 - Contracts: config, run manifest, provider interface, repo structure
- M2 - Core agent: prompt, tools, menu/hours data, provider-neutral agent API
- M3 - Provider parity: Gemini and OpenAI adapters behind one interface
- M4 - Harness: WAV injection, turn sequencing, transport-level logging, timing symmetry
- M5 - Script: record 20 WAVs, fill `utterances.yaml`
- M6 - Runs: repeated runs, raw logs to `results/`
- M7 - Review and report: sub-agent reviews, `analysis/report.md`, writeup draft
- M8 - Optional UI: thin dashboard only if it helps debugging or presenting results
- M9 - Extensibility: turn-behavior + expect-check registries, barge-in scenario, cost tracking
