# Phase 3 — Evaluation Depth

**Target version:** v0.4  
**Impact:** Makes VoxArena the most thorough voice agent eval tool available — not just "did it call the right tool" but "was the conversation actually good?"

---

## Problem

Current eval coverage:

| Metric | Current |
|--------|---------|
| Tool-call accuracy (name match) | ✅ |
| TTFA (time-to-first-audio) | ✅ |
| Hallucination detection (LLM judge) | ✅ basic |
| Argument accuracy | ❌ |
| Interruption handling | ❌ |
| Multi-turn coherence | ❌ |
| Latency percentiles (p50/p95/p99) | ❌ |
| Audio quality metrics | ❌ |
| Barge-in correctness | ❌ |

The gap between "called the right function" and "was a good voice agent" is large.

---

## What to Build

### 1. Argument-level tool accuracy

Today: did the agent call `transfer_funds`? ✅/❌  
Tomorrow: did it call `transfer_funds(amount=200, from="savings", to="checking")`?

```python
@dataclass
class ToolCallExpectation:
    name: str
    args: dict | None = None          # None = don't check args
    arg_match: Literal["exact", "partial", "semantic"] = "partial"
```

Score per turn: `args_correct / args_expected`.

### 2. Latency breakdown

Beyond TTFA, measure and store:

- `ttfa_ms` — time to first audio byte
- `transcript_latency_ms` — time to final transcript  
- `tool_call_latency_ms` — time from utterance end to tool result
- `total_turn_ms` — wall-clock time for the full turn

Report p50 / p95 / p99 across all turns in a run.

### 3. Interruption / barge-in correctness

Utterances already have `barge_in_delay_ms`. Evaluate:

- Did the agent stop speaking within N ms of the barge-in? ✅/❌
- Did it correctly process the interrupting utterance? ✅/❌

This is a differentiating metric — Gemini and OpenAI handle interruptions very differently.

### 4. Multi-turn coherence score

Use an LLM judge (already used for hallucination) to evaluate:

> "Given this conversation history and the agent's last response, did the agent maintain correct context from earlier turns?"

Score: 0.0–1.0 per turn, averaged across the run. Particularly useful for finance/banking scenarios where the agent must remember prior transfers.

### 5. Silence / no-response detection

If the agent returns empty audio or transcript after N seconds, flag as `TIMEOUT` rather than letting the run hang. Surface this in the UI as a distinct failure mode.

### 6. Audio quality score (optional / experimental)

Integrate a MOS (Mean Opinion Score) estimator (e.g. DNSMOS) to score audio naturalness. Tag as experimental — useful for comparing TTS backends.

---

## Evaluator plugin interface

Allow custom evaluators to be registered:

```python
from voxarena import register_evaluator, TurnResult

@register_evaluator("my_custom_score")
def evaluate(turn: TurnResult) -> float:
    # return 0.0–1.0
    ...
```

Custom scores appear in the UI and JSON output alongside built-in metrics.

---

## Success Criteria

- Argument accuracy is tracked and shown in the run inspector.
- Latency p50/p95 appear on the dashboard.
- Barge-in correctness is a scoreable metric for templates that use it.
- A custom evaluator can be added without modifying VoxArena source.
