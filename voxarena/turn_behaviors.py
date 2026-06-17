"""Pluggable per-turn execution strategies for the harness's drive loop.

A behavior handler owns the current turn's "wait it out" phase *and* the
lifecycle of its audio-injection task (start/await/stop) — both must be
owned together because `AudioInjectionProcessor` only supports one in-flight
injection at a time.

Each handler has the signature::

    async def handler(ctx: TurnContext, injection_task: asyncio.Task,
                       next_utt: Optional[dict]) -> Tuple[bool, Optional[asyncio.Task]]

and returns ``(turn_timed_out, pending_injection_task)``. ``pending_injection_task``
is an already-started `inject_wav` task for the *next* turn (pre-started by a
behavior like barge-in), or ``None`` if the next turn should start its own
injection normally.

Which handler runs for turn *i* is decided by turn *i+1*'s `behavior.type`
(default ``"sequential"``) — turn i+1 is the one declaring "interrupt the
previous turn". Adding a new behavior is just a new handler + registry entry;
the drive loop in `voxarena/harness.py` never needs new branches.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger
from pipecat.frames.frames import InterruptionFrame

from voxarena.providers.base import RunMetricsCollector

BehaviorResult = Tuple[bool, Optional[asyncio.Task]]


@dataclass
class TurnContext:
    task: Any  # PipelineTask
    injector: Any  # AudioInjectionProcessor
    collector: RunMetricsCollector
    manifest: Any
    utt: Dict[str, Any]
    utt_id: str


async def handle_sequential(
    ctx: TurnContext, injection_task: asyncio.Task, next_utt: Optional[Dict[str, Any]]
) -> BehaviorResult:
    """Default behavior: wait for the current turn's response to fully complete
    before moving on. This is the original `_drive_turns` wait phase, unchanged."""
    collector = ctx.collector
    turn_timed_out = False

    try:
        await asyncio.wait_for(collector.turn_completed_event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        turn_timed_out = True
        logger.warning(
            f"[Harness] Timeout waiting for response completion on {ctx.utt_id}. "
            f"Sending InterruptionFrame to abort in-flight response."
        )
        try:
            await ctx.task.queue_frame(InterruptionFrame())
        except Exception as e:
            logger.error(f"[Harness] Failed to queue InterruptionFrame: {e}")
        collector.turn_completed_event.set()
        await asyncio.sleep(1.0)

    # OpenAI Realtime emits FunctionCallInProgressFrame / FunctionCallResultFrame
    # *after* LLMFullResponseEndFrame (Gemini Live emits them before). If the
    # expect block declared a tool and we haven't seen the result yet, give the
    # late frames a brief grace window so evaluate_turn doesn't read
    # tool_call_details as None and falsely flag the turn.
    expected_tool = (ctx.utt.get("expect") or {}).get("tool")
    if expected_tool and not turn_timed_out and not collector.tool_call_completed_event.is_set():
        try:
            await asyncio.wait_for(collector.tool_call_completed_event.wait(), timeout=1.5)
            logger.debug(
                f"[Harness] Late tool-call frame arrived for {ctx.utt_id} "
                f"after LLMFullResponseEndFrame (OpenAI ordering)."
            )
        except asyncio.TimeoutError:
            logger.debug(f"[Harness] No late tool-call frame for {ctx.utt_id} within grace window.")

    ctx.injector.stop_injection()
    await injection_task
    return turn_timed_out, None


async def handle_barge_in(
    ctx: TurnContext, injection_task: asyncio.Task, next_utt: Optional[Dict[str, Any]]
) -> BehaviorResult:
    """The *next* turn declared `behavior: {"type": "barge_in"}` — start its audio
    `delay_ms` after this turn's bot starts speaking, while this turn's response
    is still in flight. This causes UserStartedSpeakingFrame to land while
    `current_turn` is still this turn and the bot is speaking, so
    `interruption_sent_at`/`interruption_stop_latency_ms` get recorded on *this*
    turn (RunMetricsCollector.process_frame, unchanged).

    If this turn's bot never starts speaking, falls back to `handle_sequential`
    and the next turn proceeds as a normal (non-barge-in) turn.
    """
    collector = ctx.collector

    try:
        # Use the same 10s ceiling as the sequential wait — turns that involve
        # a tool call (e.g. u02 here) often take 5-8s before the bot's audio
        # response actually starts, well past the original 5s timeout.
        await asyncio.wait_for(collector.bot_started_speaking_event.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.debug(
            f"[Harness] Barge-in skipped for turn after {ctx.utt_id}: "
            f"bot never started speaking within 10s. Falling back to sequential."
        )
        return await handle_sequential(ctx, injection_task, next_utt)

    # Finish this turn's own injection before starting the next one —
    # AudioInjectionProcessor supports only one in-flight injection.
    ctx.injector.stop_injection()
    await injection_task

    delay_ms = (next_utt.get("behavior") or {}).get("delay_ms", 600)
    await asyncio.sleep(delay_ms / 1000.0)

    # Hold an explicit reference to the turn we're interrupting so we can write
    # interruption_* fields by reference, independent of which turn
    # `collector.current_turn` is pointing at (it'll switch to the next turn
    # once that turn's audio starts streaming).
    interrupted_turn = collector.current_turn
    if interrupted_turn and interrupted_turn.interruption_sent_at is None:
        interrupted_turn.interruption_sent_at = time.time() * 1000.0
        logger.info(
            f"[Harness] Barge-in: interruption_sent_at recorded for {ctx.utt_id} "
            f"({delay_ms}ms after bot started speaking)."
        )

    # Explicitly cancel the in-flight response so the bot actually stops.
    # The injected UserStartedSpeakingFrame alone is not always sufficient.
    try:
        await ctx.task.queue_frame(InterruptionFrame())
    except Exception as e:
        logger.error(f"[Harness] Failed to queue InterruptionFrame on barge-in: {e}")

    next_audio_path = next_utt["_audio_path"]
    pending_injection_task = asyncio.create_task(ctx.injector.inject_wav(next_audio_path))

    # Measure when the bot actually stops emitting audio by polling
    # `last_bot_output_at` until it's been stable for `quiet_window_ms`. This
    # is the real stop signal — Gemini Live doesn't send LLMFullResponseEndFrame
    # or BotStoppedSpeakingFrame after an InterruptionFrame, so neither
    # `turn_completed_event` nor the collector's BotStoppedSpeakingFrame branch
    # can be relied on here.
    quiet_window_ms = 150
    poll_interval_s = 0.05
    max_wait_s = 1.5
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        last = collector.last_bot_output_at
        if last is not None and (time.time() * 1000.0 - last) >= quiet_window_ms:
            break
        await asyncio.sleep(poll_interval_s)

    if interrupted_turn and interrupted_turn.interruption_sent_at and interrupted_turn.interruption_stopped_at is None:
        stopped_ms = collector.last_bot_output_at or (time.time() * 1000.0)
        delta = stopped_ms - interrupted_turn.interruption_sent_at
        if delta < 0:
            # Bot already finished streaming audio before we sent the interruption
            # — nothing to actually interrupt. Latency isn't meaningful here.
            logger.info(
                f"[Harness] Barge-in: bot already stopped {-delta:.0f}ms before "
                f"interruption for {ctx.utt_id}; recording no stop latency."
            )
            interrupted_turn.interruption_stopped_at = None
            interrupted_turn.interruption_stop_latency_ms = None
        else:
            interrupted_turn.interruption_stopped_at = stopped_ms
            interrupted_turn.interruption_stop_latency_ms = delta
            logger.info(
                f"[Harness] Barge-in: interruption_stop_latency_ms="
                f"{delta:.0f}ms for {ctx.utt_id}."
            )

    return False, pending_injection_task


# Keyed by the *next* turn's `behavior.type`. Adding a new turn-execution
# strategy is a new handler + entry here, not a new branch in `_drive_turns`.
BEHAVIOR_HANDLERS: Dict[str, Callable] = {
    "sequential": handle_sequential,
    "barge_in": handle_barge_in,
}
