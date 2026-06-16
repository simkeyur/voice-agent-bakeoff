"""Pluggable `expect` checks for scoring a completed turn.

Each checker takes the turn and its `expect` block and returns
``(passed, notes, hallucination_delta)``:

- ``passed``: ``True``/``False``, or ``None`` if the check doesn't apply to
  this turn (e.g. the expected key wasn't declared).
- ``notes``: human-readable explanations to append to the turn's
  ``evaluation_notes``.
- ``hallucination_delta``: amount to add to ``turn.hallucination_count``.

``check_tool`` runs on every turn (an absent ``tool`` key means "no tool call
expected", and an unexpected call is a hallucination). All other checks only
run when their key is present in ``expect`` — see ``ALWAYS_RUN`` in
``evaluate_turn`` (voxarena/providers/base.py).
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from voxarena.manifest import TurnMetric

CheckOutcome = Tuple[Optional[bool], List[str], int]


def _args_match(expected: Any, actual: Any) -> bool:
    """Loosely compare an expected tool argument against the actual value, tolerating
    case and numeric/string formatting differences (e.g. "Friday" vs "friday", 4 vs "4")."""
    if actual is None:
        return False
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    try:
        return float(expected) == float(actual)
    except (TypeError, ValueError):
        return str(expected).strip().lower() == str(actual).strip().lower()


def check_tool(turn: TurnMetric, expect: Dict[str, Any]) -> CheckOutcome:
    expected_tool = expect.get("tool")
    expected_args = expect.get("args") or {}
    actual_tool = turn.tool_call_details.get("name") if turn.tool_call_details else None
    actual_args = (turn.tool_call_details.get("args") or {}) if turn.tool_call_details else {}

    if expected_tool is None:
        if actual_tool is not None:
            return False, [f"Unexpected tool call '{actual_tool}' (none expected)."], 1
        return None, [], 0

    # Skip the check on turns that were deliberately cut short by a barge-in
    # before the bot got a chance to issue the tool call.
    if turn.interruption_sent_at is not None and actual_tool is None:
        return None, ["Tool call check skipped; turn cut short by barge-in."], 0

    if actual_tool != expected_tool:
        return False, [f"Expected tool '{expected_tool}', got '{actual_tool or 'none'}'."], 0

    notes: List[str] = []
    tool_correct = True
    for key, expected_val in expected_args.items():
        actual_val = actual_args.get(key)
        if not _args_match(expected_val, actual_val):
            tool_correct = False
            notes.append(f"Arg '{key}' mismatch: expected {expected_val!r}, got {actual_val!r}.")
    return tool_correct, notes, 0


def check_response_contains(turn: TurnMetric, expect: Dict[str, Any]) -> CheckOutcome:
    response_contains = expect.get("response_contains")
    if not response_contains:
        return None, [], 0

    if turn.interruption_sent_at is not None:
        return None, ["Response cut short by barge-in; content check skipped."], 0

    transcript_lower = (turn.transcript_output or "").lower()
    missing = [phrase for phrase in response_contains if phrase.lower() not in transcript_lower]
    if missing:
        return False, [f"Response missing expected phrase(s): {', '.join(missing)}."], 0
    return True, [], 0


def check_interrupted(turn: TurnMetric, expect: Dict[str, Any]) -> CheckOutcome:
    expected = expect.get("interrupted")
    if expected is None:
        return None, [], 0

    actual = turn.interruption_sent_at is not None
    if actual != expected:
        return False, [f"Expected interrupted={expected}, got {actual}."], 0
    return True, [], 0


# Keyed by the `expect` field each checker is responsible for. `evaluate_turn`
# always runs "tool" (see ALWAYS_RUN); the rest only run when their key is
# present in `expect`. Adding a new check type is just a new function + entry.
EXPECT_CHECKS: Dict[str, Callable[[TurnMetric, Dict[str, Any]], CheckOutcome]] = {
    "tool": check_tool,
    "response_contains": check_response_contains,
    "interrupted": check_interrupted,
}

ALWAYS_RUN = {"tool"}
