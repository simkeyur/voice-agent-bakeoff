# Phased Plan

## Phase 0 - Repo + contracts

Goal: establish the shape of the app before any provider-specific work.

Deliverables:

- Project skeleton, dependencies, and environment variables.
- Shared config model for provider, model, transport, prompt version, and run metadata.
- One run-manifest format that every later phase writes to.

Exit criteria:

- A fresh checkout can identify the active provider and model from config.
- No agent code imports vendor-specific services directly.

## Phase 1 - Core agent model

Goal: define the stable center of the app.

Deliverables:

- Shared system prompt for the Saffron Leaf agent.
- Tool schemas and deterministic fake data.
- Static menu and hours sources.
- A provider-neutral agent API that consumes prompt plus tools plus config.

Exit criteria:

- The agent logic is unchanged regardless of provider.
- Tool schemas are byte-identical across providers.

## Phase 2 - Provider adapters

Goal: make providers interchangeable at the boundary.

Deliverables:

- Thin adapter for Gemini Live.
- Thin adapter for OpenAI Realtime.
- Normalized session lifecycle, audio I/O, tool call, and usage reporting.
- One provider selection path driven by config only.

Exit criteria:

- Switching provider changes only the adapter layer and run metadata.
- The same agent and harness code can execute against every supported provider.

## Phase 3 - Reproducible harness

Goal: make the arena measurable and repeatable.

Deliverables:

- Direct audio injection for scripted runs.
- Turn sequencing and interruption control.
- Transport-layer timestamps and transcript capture.
- Immutable raw artifacts per run.

Exit criteria:

- A dry run produces symmetric timing data for every provider.
- The instrumentation gotcha is resolved before real runs begin.

## Phase 4 - Script and evaluation

Goal: lock the benchmark and score it consistently.

Deliverables:

- `utterances.yaml` with expectations for each scripted turn.
- Twenty recorded WAVs used across all runs.
- Sub-agent review prompts and scored outputs.
- Metrics summary across repeated runs per provider.

Exit criteria:

- Any provider can be replayed against the same test corpus without editing code.
- Evaluation reads artifacts; it does not mutate them.

## Phase 5 - Reporting and iteration

Goal: turn run data into a clear comparison and a reusable template.

Deliverables:

- `analysis/report.md` with results, failure modes, and recommendation.
- A writeup draft for blog or LinkedIn.
- Notes on what should stay stable for future provider swaps.

Exit criteria:

- The app is documented well enough that a new provider can be added by following the same contract.

## Phase 6 - Optional UI layer

Goal: add a thin interface only after the core workflow is proven.

Deliverables:

- Minimal black-and-white control panel for launching runs and viewing results.
- Metrics view with chart-based showdown summaries for eval results.
- Run history and artifact browser.

Exit criteria:

- The UI is strictly additive; it does not own the agent logic or provider integration.
- The visual system stays minimal, monochrome, and operational rather than decorative.

## Milestones

- M1 - Contracts: config, run manifest, provider interface, repo structure
- M2 - Core agent: prompt, tools, menu/hours data, provider-neutral agent API
- M3 - Provider parity: Gemini and OpenAI adapters behind one interface
- M4 - Harness: WAV injection, turn sequencing, transport-level logging, timing symmetry
- M5 - Script: record 20 WAVs, fill `utterances.yaml`
- M6 - Runs: repeated runs, raw logs to `results/`
- M7 - Review and report: sub-agent reviews, `analysis/report.md`, writeup draft
- M8 - Optional UI: thin dashboard only if it helps debugging or presenting results
