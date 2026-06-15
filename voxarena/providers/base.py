import time
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from pydantic import BaseModel

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.services.llm_service import FunctionCallParams
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMTextFrame,
    LLMFullResponseEndFrame
)
from voxarena.agent import Agent
from voxarena.config import ProviderConfig
from voxarena.manifest import RunManifest, TurnMetric
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

class RunMetricsCollector(FrameProcessor):
    """Pipeline processor to capture symmetric, transport-level timestamps for latency analysis."""
    
    def __init__(self, manifest: RunManifest):
        super().__init__()
        self.manifest = manifest
        self.current_turn: Optional[TurnMetric] = None
        self.last_bot_speaking_state = False
        self.turn_completed_event = asyncio.Event()
        self.bot_started_speaking_event = asyncio.Event()
        self.current_expect: Dict[str, Any] = {}

    def on_input_injected(self, utterance_id: str, text: str, expect: Optional[Dict[str, Any]] = None):
        """Programmatically register a turn start from the harness."""
        now_ms = time.time() * 1000.0
        self.turn_completed_event.clear()
        self.bot_started_speaking_event.clear()
        self.current_expect = expect or {}

        self.current_turn = TurnMetric(
            utterance_id=utterance_id,
            text_input=text,
            input_sent_at=now_ms
        )
        self.manifest.turns.append(self.current_turn)
        logger.debug(f"[MetricsCollector] Turn {utterance_id} started at {now_ms:.2f} ms")

    def evaluate_turn(self):
        """Score the just-completed turn against its expected tool call and response content."""
        turn = self.current_turn
        if not turn:
            return

        expect = self.current_expect
        expected_tool = expect.get("tool")
        expected_args = expect.get("args") or {}
        actual_tool = turn.tool_call_details.get("name") if turn.tool_call_details else None
        actual_args = (turn.tool_call_details.get("args") or {}) if turn.tool_call_details else {}

        notes = []
        tool_correct = None

        if expected_tool is None:
            if actual_tool is not None:
                tool_correct = False
                turn.hallucination_count = (turn.hallucination_count or 0) + 1
                notes.append(f"Unexpected tool call '{actual_tool}' (none expected).")
        else:
            if actual_tool != expected_tool:
                tool_correct = False
                notes.append(f"Expected tool '{expected_tool}', got '{actual_tool or 'none'}'.")
            else:
                tool_correct = True
                for key, expected_val in expected_args.items():
                    actual_val = actual_args.get(key)
                    if not _args_match(expected_val, actual_val):
                        tool_correct = False
                        notes.append(f"Arg '{key}' mismatch: expected {expected_val!r}, got {actual_val!r}.")

        response_contains = expect.get("response_contains")
        response_match = None
        if response_contains:
            transcript_lower = (turn.transcript_output or "").lower()
            missing = [phrase for phrase in response_contains if phrase.lower() not in transcript_lower]
            response_match = not missing
            if missing:
                notes.append(f"Response missing expected phrase(s): {', '.join(missing)}.")

        turn.tool_call_correct = tool_correct
        turn.response_match = response_match
        turn.evaluation_passed = (tool_correct is not False) and (response_match is not False)
        if notes:
            turn.evaluation_notes = " ".join(notes)

    async def process_frame(self, frame: Frame, direction) -> Frame:
        now_ms = time.time() * 1000.0
        
        # 1. Capture User Audio Injection (Input) - fallback only
        if isinstance(frame, InputAudioRawFrame):
            if not self.current_turn:
                self.on_input_injected(f"u_{int(now_ms)}", "")
                logger.debug(f"[MetricsCollector] Fallback Turn started. Input injected at {now_ms:.2f} ms")

        # 2. Capture Tool/Function Call events
        elif isinstance(frame, FunctionCallInProgressFrame):
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

        # 3. Capture Bot Output Audio (First Audio response)
        elif isinstance(frame, (OutputAudioRawFrame, BotStartedSpeakingFrame)):
            if self.current_turn and not self.current_turn.first_audio_received_at:
                self.current_turn.first_audio_received_at = now_ms
                self.current_turn.time_to_first_audio_ms = now_ms - self.current_turn.input_sent_at
                logger.info(f"[MetricsCollector] Time-to-First-Audio (TTFA): {self.current_turn.time_to_first_audio_ms:.2f} ms")
            
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
                self.current_turn.interruption_stopped_at = now_ms
                self.current_turn.interruption_stop_latency_ms = now_ms - self.current_turn.interruption_sent_at
                logger.info(f"[MetricsCollector] Bot stopped speaking after interruption in {self.current_turn.interruption_stop_latency_ms:.2f} ms")

        # 5. Capture bot transcript text
        # Gemini Live pushes both an LLMTextFrame and a TTSTextFrame
        # (a TextFrame subclass) for the same text chunk, so only the
        # LLMTextFrame is captured here to avoid double-appending.
        elif isinstance(frame, LLMTextFrame):
            if self.current_turn:
                self.current_turn.transcript_output += frame.text

        # 6. Capture response completion
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self.current_turn:
                self.current_turn.audio_completed_received_at = now_ms
                logger.info(f"[MetricsCollector] Turn {self.current_turn.utterance_id} response completed.")
            self.turn_completed_event.set()

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
