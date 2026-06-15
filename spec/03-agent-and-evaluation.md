# Agent and Evaluation

## Agent

- Persona: FAQ bot for a fictional vegetarian restaurant called Saffron Leaf.
- Menu is strictly vegetarian, with no onion and no garlic.
- The agent should be useful, factual, and constrained.

## Shared Prompt

Use one shared system prompt file for every provider. The prompt must be byte-identical across providers unless the same change is applied everywhere.

## Shared Tools

All providers must expose the same JSON schemas.

1. `lookup_menu(category)` returns items from a static JSON menu.
2. `get_hours(day)` returns hours from a static table.
3. `check_reservation_availability(date, time, party_size)` returns deterministic fake availability.

## Test Script

The benchmark uses 20 scripted utterances:

- Simple FAQ turns
- Tool-call triggers
- Interruptions
- Ambiguous or mumbled speech
- Code-switching
- Constraint probes

Each utterance should be stored in `utterances.yaml` with expected outcomes.

Example:

```yaml
- id: u07
  text: "Can I book a table for six tomorrow at seven pm"
  expect:
    tool: check_reservation_availability
    args: { party_size: 6, time: "19:00" }
```

### `behavior` (optional, per-utterance)

Declares how the harness should drive this turn relative to the *previous*
turn. Default is `"sequential"` (wait for the previous turn's response to
fully complete before injecting this turn's audio).

```yaml
- id: u07
  text: "Wait, actually, is The Bistro open on Mondays?"
  behavior:
    type: "barge_in"
    delay_ms: 600   # start this turn's audio 600ms after the previous turn's bot starts speaking
```

`barge_in` causes `UserStartedSpeakingFrame` to be observed while the
*previous* turn is still mid-response, so that turn's
`interruption_sent_at`/`interruption_stopped_at`/
`interruption_stop_latency_ms` get populated. If the previous turn's bot
never starts speaking within a short window, the harness falls back to
`sequential` for both turns.

Adding a new `behavior.type` means adding a handler to
`BEHAVIOR_HANDLERS` in `voxarena/turn_behaviors.py` — no changes to
`voxarena/harness.py`'s drive loop.

### `expect` schema

- `tool` / `args` — expected tool call and (loosely-matched) arguments.
  Absence of `tool` means "no tool call expected"; an unexpected call counts
  as a hallucination.
- `response_contains` — list of phrases the transcript must contain (skipped,
  not failed, if the turn was cut short by a barge-in).
- `interrupted` (bool) — asserts whether `interruption_sent_at` was recorded
  for this turn. Used by the interrupted half of a barge-in pair.

Each key is handled by an independent checker in `EXPECT_CHECKS`
(`voxarena/evaluators.py`); unknown keys are ignored, so new check types are
forward-compatible with old run data.

## Metrics

Measure per turn and per run.

- Time-to-first-audio
- Tool-call accuracy
- Interruption stop latency — exercised via `barge_in` utterances (see above)
- Transcript fidelity — **future work** (Phase 8); `transcript_fidelity_score`
  is currently always `null`
- Hallucination count
- Cost per conversation — via Pipecat usage-metrics frames
  (`prompt_tokens`/`completion_tokens` per turn) and a flat per-model
  $/token table in `voxarena/pricing.py`. This is a blended approximation
  (audio vs. text tokens aren't broken out), good for relative provider
  comparison, not exact billing reconciliation. `cost_usd` is `null` for
  turns whose model has no pricing entry.

## Instrumentation Constraint

Use transport-layer timestamps for every provider. Do not compare one provider at the service layer and another at the observer layer.

Pipecat's `GeminiLiveLLMService` does not emit `UserStartedSpeakingFrame` or `UserStoppedSpeakingFrame` with default server-side VAD, so turn-based observers can be asymmetric. Fix this with a custom transport-boundary logger or locally-driven turn detection before doing real runs.

## Review Loop

Each reviewer should do one narrow job only:

1. Tool accuracy reviewer: transcript + tool-call log + ground truth YAML.
2. Hallucination reviewer: transcript + menu/hours JSON.
3. Failure-pattern comparator: scored results from both providers.
