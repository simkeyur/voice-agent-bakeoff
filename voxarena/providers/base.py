import time
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import (
    Frame,
    OutputAudioRawFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMTextFrame,
    LLMFullResponseEndFrame,
    MetricsFrame,
)
from pipecat.metrics.metrics import LLMUsageMetricsData
from voxarena.agent import Agent
from voxarena.config import ProviderConfig
from voxarena.evaluators import ALWAYS_RUN, EXPECT_CHECKS
from voxarena.manifest import RunManifest, TurnMetric
from voxarena.pricing import estimate_cost
from voxarena.tools import execute_tool


async def shared_tool_callback(params: FunctionCallParams) -> None:
    """Provider-agnostic function callback for handling tool calls from the realtime LLM."""
    name = params.function_name
    args = params.arguments
    logger.info(f"[Tool] {name}({args})")
    try:
        result_str = execute_tool(name, args)
        await params.result_callback({"result": result_str})
    except Exception as e:
        logger.error(f"[Tool] Error in {name}: {e}")
        await params.result_callback({"error": str(e)})


class RunMetricsCollector(FrameProcessor):
    """Pipeline processor to capture symmetric, transport-level timestamps for latency analysis."""
    
    def __init__(self, manifest: RunManifest):
        super().__init__()
        self.manifest = manifest
        self.current_turn: Optional[TurnMetric] = None
        self.last_bot_speaking_state = False
        self.turn_completed_event = asyncio.Event()
        self.bot_started_speaking_event = asyncio.Event()
        # Fires on FunctionCallResultFrame so the harness can wait for late
        # tool-call frames (OpenAI Realtime emits the function-call event
        # *after* LLMFullResponseEndFrame, unlike Gemini Live).
        self.tool_call_completed_event = asyncio.Event()
        self.current_expect: Dict[str, Any] = {}
        # Timestamp of the most recent OutputAudioRawFrame from the bot. Used by
        # the barge-in handler to measure when the bot actually stops emitting
        # audio (Gemini Live doesn't send LLMFullResponseEndFrame after an
        # InterruptionFrame, so this is the only reliable stop signal).
        self.last_bot_output_at: Optional[float] = None

    def on_input_injected(self, utterance_id: str, text: str, expect: Optional[Dict[str, Any]] = None):
        """Programmatically register a turn start from the harness."""
        now_ms = time.time() * 1000.0
        self.turn_completed_event.clear()
        self.bot_started_speaking_event.clear()
        self.tool_call_completed_event.clear()
        self.current_expect = expect or {}

        self.current_turn = TurnMetric(
            utterance_id=utterance_id,
            text_input=text,
            input_sent_at=now_ms
        )
        self.manifest.turns.append(self.current_turn)
        logger.debug(f"[MetricsCollector] Turn {utterance_id} started at {now_ms:.2f} ms")

    def evaluate_turn(self):
        """Score the just-completed turn against its `expect` block by running every
        applicable checker in EXPECT_CHECKS (voxarena/evaluators.py)."""
        turn = self.current_turn
        if not turn:
            return

        expect = self.current_expect
        notes = []
        results: Dict[str, Optional[bool]] = {}

        for key, checker in EXPECT_CHECKS.items():
            if key not in expect and key not in ALWAYS_RUN:
                continue
            passed, check_notes, hallucination_delta = checker(turn, expect)
            results[key] = passed
            notes.extend(check_notes)
            if hallucination_delta:
                turn.hallucination_count = (turn.hallucination_count or 0) + hallucination_delta

        turn.tool_call_correct = results.get("tool")
        turn.response_match = results.get("response_contains")
        turn.evaluation_passed = all(passed is not False for passed in results.values())
        if notes:
            turn.evaluation_notes = " ".join(notes)

        turn.cost_usd = estimate_cost(self.manifest.model, turn.prompt_tokens, turn.completion_tokens)

    async def process_frame(self, frame: Frame, direction) -> Frame:
        now_ms = time.time() * 1000.0

        # 2. Capture Tool/Function Call events
        if isinstance(frame, FunctionCallInProgressFrame):
            if self.current_turn:
                logger.debug(f"[MetricsCollector] Tool call detected for {frame.function_name}")
                if not self.current_turn.tool_call_details:
                    self.current_turn.tool_call_details = {
                        "name": frame.function_name,
                        "args": frame.arguments or {},
                        "called_at": now_ms
                    }

        elif isinstance(frame, FunctionCallResultFrame):
            if self.current_turn and self.current_turn.tool_call_details:
                call_at = self.current_turn.tool_call_details.get("called_at", now_ms)
                self.current_turn.tool_call_details["result_received_at"] = now_ms
                self.current_turn.tool_call_details["latency_ms"] = now_ms - call_at
                logger.debug(f"[MetricsCollector] Tool call resolved in {now_ms - call_at:.2f} ms")
            # Wake the harness even when current_turn is None — but the harness
            # also reads current_turn before deciding what to do.
            self.tool_call_completed_event.set()

        # 3. Capture Bot Output Audio (First Audio response)
        elif isinstance(frame, (OutputAudioRawFrame, BotStartedSpeakingFrame)):
            if self.current_turn and not self.current_turn.first_audio_received_at:
                self.current_turn.first_audio_received_at = now_ms
                self.current_turn.time_to_first_audio_ms = now_ms - self.current_turn.input_sent_at
                logger.info(f"[MetricsCollector] Time-to-First-Audio (TTFA): {self.current_turn.time_to_first_audio_ms:.2f} ms")

            if isinstance(frame, OutputAudioRawFrame):
                self.last_bot_output_at = now_ms

            self.bot_started_speaking_event.set()
            if not self.last_bot_speaking_state:
                self.last_bot_speaking_state = True
                
        # 4. Handle Interruption latencies
        elif isinstance(frame, UserStartedSpeakingFrame):
            # If the user started speaking while the bot was speaking, record interruption
            if self.last_bot_speaking_state and self.current_turn:
                self.current_turn.interruption_sent_at = now_ms
                logger.info(f"[MetricsCollector] User interruption detected at {now_ms:.2f} ms")

        elif isinstance(frame, BotStoppedSpeakingFrame):
            self.last_bot_speaking_state = False
            if self.current_turn and self.current_turn.interruption_sent_at and not self.current_turn.interruption_stopped_at:
                delta = now_ms - self.current_turn.interruption_sent_at
                if delta < 0:
                    logger.debug(
                        f"[MetricsCollector] BotStoppedSpeakingFrame predates interruption "
                        f"by {-delta:.0f}ms; skipping stop-latency record."
                    )
                else:
                    self.current_turn.interruption_stopped_at = now_ms
                    self.current_turn.interruption_stop_latency_ms = delta
                    logger.info(f"[MetricsCollector] Bot stopped speaking after interruption in {delta:.2f} ms")

        # 5. Capture bot transcript text
        # Gemini Live pushes both an LLMTextFrame and a TTSTextFrame
        # (a TextFrame subclass) for the same text chunk, so only the
        # LLMTextFrame is captured here to avoid double-appending.
        elif isinstance(frame, LLMTextFrame):
            if self.current_turn:
                self.current_turn.transcript_output += frame.text

        # 6b. Capture LLM token usage for cost estimation
        elif isinstance(frame, MetricsFrame):
            if self.current_turn:
                for entry in frame.data:
                    if isinstance(entry, LLMUsageMetricsData):
                        usage = entry.value
                        self.current_turn.prompt_tokens = usage.prompt_tokens
                        self.current_turn.completion_tokens = usage.completion_tokens
                        self.current_turn.cost_usd = estimate_cost(
                            self.manifest.model, usage.prompt_tokens, usage.completion_tokens
                        )

        # 6. Capture response completion
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self.current_turn:
                self.current_turn.audio_completed_received_at = now_ms
                logger.info(f"[MetricsCollector] Turn {self.current_turn.utterance_id} response completed.")
                self.turn_completed_event.set()
            else:
                # Late end-frame from an abandoned turn — discard so it can't
                # wake up the next turn's wait_for or pollute its metrics.
                logger.debug("[MetricsCollector] Discarded stray LLMFullResponseEndFrame (no current turn).")

        # Continue propagating the frame
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

class BaseProviderAdapter:
    """Abstract base class for Gemini Live and OpenAI Realtime Pipecat adapters."""
    
    def __init__(self, agent: Agent, config: ProviderConfig, manifest: RunManifest):
        self.agent = agent
        self.config = config
        self.manifest = manifest
        self.metrics_collector = RunMetricsCollector(manifest)

    def get_llm_service(self) -> Any:
        """Instantiate and return the vendor-specific Pipecat LLM/Realtime Service."""
        raise NotImplementedError("Subclasses must implement get_llm_service")

    def register_tools(self, service: Any) -> None:
        """Wire every agent tool into the Pipecat service using a template-aware callback."""
        async def tool_callback(params: FunctionCallParams) -> None:
            name = params.function_name
            args = params.arguments
            logger.info(f"[Tool] {name}({args}) using template {self.agent.template_id}")
            try:
                result_str = execute_tool(name, args, template_id=self.agent.template_id)
                await params.result_callback({"result": result_str})
            except Exception as e:
                logger.error(f"[Tool] Error in {name}: {e}")
                await params.result_callback({"error": str(e)})

        for schema in self.agent.tool_schemas:
            service.register_function(schema["name"], tool_callback)
