import os
import time
import wave
import asyncio
from typing import List, Dict, Any, Optional
from loguru import logger

from pipecat.processors.frame_processor import FrameProcessor
from pipecat.frames.frames import (
    Frame,
    InputAudioRawFrame,
    OutputAudioRawFrame,
    EndFrame,
    InterruptionFrame,
    StopTaskFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.runner import PipelineRunner

from voxarena.agent import Agent
from voxarena.audio_cache import resolve_audio
from voxarena.config import ProviderConfig, settings
from voxarena.database import load_utterances_from_db
from voxarena.manifest import RunManifest, TurnMetric, AggregateMetrics
from voxarena.providers import make_adapter

class AudioInjectionProcessor(FrameProcessor):
    """Processor designed to stream raw PCM audio frames into the pipeline in real-time."""
    
    def __init__(self):
        super().__init__()
        self._injecting = False
        self.task = None

    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)

    async def push_frame_safe(self, frame: Frame):
        if self.task:
            await self.task.queue_frame(frame)
        else:
            await self.push_frame(frame)

    async def inject_wav(self, file_path: str):
        """Read a WAV file and push its PCM chunks into the pipeline at a real-time rate."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
            
        self._injecting = True
        logger.info(f"[Harness] Starting audio injection from {os.path.basename(file_path)}")
        
        # Send speaking started signal downstream
        await self.push_frame_safe(UserStartedSpeakingFrame())
        
        with wave.open(file_path, "rb") as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            
            # We want 20ms chunks.
            # Number of frames in 20ms = sample_rate * 0.02
            chunk_frames = int(sample_rate * 0.02)
            chunk_bytes = chunk_frames * channels * sampwidth
            
            data = wf.readframes(chunk_frames)
            while data and self._injecting:
                frame = InputAudioRawFrame(
                    audio=data,
                    sample_rate=sample_rate,
                    num_channels=channels
                )
                await self.push_frame_safe(frame)
                # Sleep to simulate real-time playback
                await asyncio.sleep(0.02)
                data = wf.readframes(chunk_frames)
                
        # Send speaking stopped signal downstream
        await self.push_frame_safe(UserStoppedSpeakingFrame())
        self._injecting = False
        logger.info("[Harness] Audio injection complete.")

    def stop_injection(self):
        self._injecting = False


class AudioCaptureProcessor(FrameProcessor):
    """Processor to capture and record the bot's raw audio response frames."""
    
    def __init__(self, output_dir: str):
        super().__init__()
        self.output_dir = output_dir
        self.current_utterance_id: Optional[str] = None
        self.audio_data = bytearray()
        self.sample_rate = 24000
        self.channels = 1
        self.sampwidth = 2

    def start_turn(self, utterance_id: str):
        self.current_utterance_id = utterance_id
        self.audio_data = bytearray()

    async def process_frame(self, frame: Frame, direction) -> Frame:
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            self.audio_data.extend(frame.audio)
            self.sample_rate = frame.sample_rate
            self.channels = frame.num_channels
            
        await self.push_frame(frame, direction)

    def save_turn_audio(self) -> Optional[str]:
        if not self.current_utterance_id or not self.audio_data:
            return None
            
        output_path = os.path.join(
            self.output_dir, f"{self.current_utterance_id}_response.wav"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sampwidth)
            wf.setframerate(self.sample_rate)
            wf.writeframes(bytes(self.audio_data))
            
        logger.debug(f"[Harness] Saved bot response audio to {output_path}")
        return output_path


class EvaluationHarness:
    """Manages the full automated execution of the 20-utterance test suite against a provider."""
    
    def __init__(self, config: ProviderConfig, agent: Agent, api_key: str, run_id: Optional[str] = None):
        self.config = config
        self.agent = agent
        self.api_key = api_key
        self.stop_requested = False
        self.injector = None
        self.task = None
        
        # Setup Run ID and directories
        self.run_id = run_id or f"run_{int(time.time())}"
        self.run_dir = os.path.join(settings.RESULTS_DIR, self.config.provider, self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        
        # Initialize Manifest
        manifest_path = os.path.join(self.run_dir, "manifest.json")
        self.manifest = RunManifest(
            run_id=self.run_id,
            provider=self.config.provider,
            model=self.config.model,
            transport=self.config.transport,
            prompt_version=self.agent.prompt_version,
            prompt_hash=self.agent.prompt_hash,
            tool_schema_version=self.agent.tool_schema_version,
            tool_schema_hash=self.agent.tool_schema_hash,
            template_id=self.agent.template_id,
            manifest_path=manifest_path,
        )
        
        # Instantiate the registered adapter for this provider
        self.adapter = make_adapter(
            self.config.provider, self.agent, self.config, self.manifest, self.api_key
        )

    def stop(self):
        """Request the session to stop prematurely."""
        logger.info(f"[Harness] Stop requested for run {self.run_id}")
        self.stop_requested = True
        if self.injector:
            self.injector.stop_injection()
        if hasattr(self, "adapter") and self.adapter and self.adapter.metrics_collector:
            self.adapter.metrics_collector.turn_completed_event.set()

    async def run_session(self, utterances: Optional[List[Dict[str, Any]]] = None, num_turns: Optional[int] = None):
        """Executes the test suite inside a single continuous Pipecat session.

        The harness no longer reads scripts from disk — the CLI parses files and
        passes the resulting list in; the UI passes ``None`` and the harness
        loads from SQLite. There is no implicit fallback script.
        """
        if utterances is None:
            try:
                utterances = load_utterances_from_db()
            except Exception as e:
                raise RuntimeError(f"Failed to load utterances from SQLite: {e}") from e

        if not utterances:
            raise RuntimeError(
                "No utterances available for this run. "
                "Add turns via the UI editor or pass --script to the CLI."
            )

        if num_turns is not None and num_turns > 0:
            utterances = utterances[:num_turns]


        # Resolve audio for every utterance up front (hash-keyed cache; TTS
        # synthesis on miss). Done before the pipeline starts so per-turn
        # latency measurements aren't polluted by TTS time. Run in a thread
        # so the synchronous TTS calls don't block the event loop.
        async def _resolve_one(utt):
            utt["_audio_path"] = await asyncio.to_thread(resolve_audio, utt["text"])

        await asyncio.gather(*[_resolve_one(utt) for utt in utterances])
        
        # 2. Build Pipeline
        llm_service = self.adapter.get_llm_service()
        injector = self.injector = AudioInjectionProcessor()
        capture = AudioCaptureProcessor(self.run_dir)
        collector = self.adapter.metrics_collector
        context_aggregator = LLMContextAggregatorPair(LLMContext(messages=[]))

        # Pipeline: Injector -> LLM Service -> Capture -> Metrics Collector -> Assistant Context Aggregator
        # Capture/Collector are pure pass-through observers and must run
        # before the assistant aggregator, which consumes LLMTextFrame and
        # LLMFullResponseEndFrame for its own aggregation and would
        # otherwise prevent them from reaching the collector. The aggregator
        # turns FunctionCallResultFrame into an LLMContextFrame pushed
        # upstream, which is what tells the Gemini Live service to continue
        # the turn after a tool call.
        pipeline = Pipeline([
            injector,
            llm_service,
            capture,
            collector,
            context_aggregator.assistant()
        ])
        
        runner = PipelineRunner()
        task = self.task = PipelineTask(pipeline)
        injector.task = task
        
        # Start Pipecat pipeline task in background
        logger.info(f"[Harness] Starting pipeline runner task for {self.config.provider}...")
        self.manifest.status = "running"
        await self.manifest.save_progress_async()
        
        runner_task = asyncio.create_task(runner.run(task))
        
        # Wait a moment for session connection to establish
        await asyncio.sleep(2.0)
        
        # Initialize initial context frame to trigger Gemini/OpenAI session initialization.
        # Both Gemini Live and OpenAI Realtime immediately generate a response from this
        # empty context (an unprompted "greeting"). If we start turn 1 before that response
        # finishes, its trailing text/audio frames get attributed to turn 1 (and the
        # AudioCaptureProcessor buffer for turn 1 starts out already containing its audio),
        # causing turn 1's transcript/audio to look like a continuation of an unrelated
        # response. So we drain this spurious response to completion first.
        from pipecat.frames.frames import LLMContextFrame
        logger.info("[Harness] Queueing initial LLMContextFrame...")
        collector.turn_completed_event.clear()
        await task.queue_frame(LLMContextFrame(LLMContext(messages=[])))
        try:
            await asyncio.wait_for(collector.turn_completed_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("[Harness] Timed out waiting for initial context response to complete.")
        collector.turn_completed_event.clear()
        await asyncio.sleep(0.5)
        
        # Session-wide cap: each turn's own 15s wait + 2s reflection ~= 20s, plus
        # generous headroom for slow provider startup. Prevents a wedged Pipecat
        # WebSocket from blocking the run forever.
        session_timeout_sec = max(60.0, len(utterances) * 30.0)

        async def _drive_turns():
            for i, utt in enumerate(utterances):
                if self.stop_requested:
                    logger.info("[Harness] Stop requested before turn injection, breaking.")
                    break

                utt_id = utt["id"]
                text = utt["text"]
                logger.info(f"\n--- [Harness] Turn {i+1}/{len(utterances)}: {utt_id} - '{text}' ---")

                collector.on_input_injected(utt_id, text, utt.get("expect"))
                capture.start_turn(utt_id)

                await self.manifest.save_progress_async(collector.current_turn)

                audio_path = utt["_audio_path"]
                injection_task = asyncio.create_task(injector.inject_wav(audio_path))

                try:
                    await asyncio.wait_for(collector.turn_completed_event.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[Harness] Timeout waiting for response completion on {utt_id}.")
                    collector.turn_completed_event.set()

                injector.stop_injection()
                await injection_task

                if self.stop_requested:
                    logger.info("[Harness] Stop requested during turn wait, breaking.")
                    break

                saved_audio = capture.save_turn_audio()
                if collector.current_turn:
                    collector.current_turn.audio_output_path = saved_audio

                collector.evaluate_turn()
                await self.manifest.save_progress_async(collector.current_turn)
                await asyncio.sleep(2.0)

        timed_out = False
        try:
            try:
                await asyncio.wait_for(_drive_turns(), timeout=session_timeout_sec)
            except asyncio.TimeoutError:
                logger.error(f"[Harness] Session timeout exceeded ({session_timeout_sec:.0f}s). Forcing shutdown.")
                timed_out = True
                self.stop_requested = True

            # 4. Graceful Shutdown
            logger.info("[Harness] All turns executed or stopped. Stopping pipeline task...")
            if not runner_task.done():
                await task.queue_frame(EndFrame())
                try:
                    await asyncio.wait_for(runner_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("[Harness] Runner task did not stop in time, cancelling.")
                    runner_task.cancel()

            # 5. Compile Final Run Results
            self.manifest.completed_at = time.time()
            if timed_out:
                self.manifest.status = "failed"
                self.manifest.error_message = f"Session timed out after {session_timeout_sec:.0f}s."
            elif self.stop_requested:
                self.manifest.status = "failed"
                self.manifest.error_message = "Run stopped by user."
            else:
                self.manifest.status = "completed"

            self.compile_aggregates()
            await self.manifest.save_async()
            logger.info(f"[Harness] Manifest saved to {self.manifest.manifest_path}")

        except Exception as e:
            logger.error(f"[Harness] Run failed with exception: {e}")
            self.manifest.status = "failed"
            self.manifest.error_message = str(e)
            await self.manifest.save_async()
            if not runner_task.done():
                await task.queue_frame(EndFrame())
                await runner_task

    def compile_aggregates(self):
        """Compile averages and rates from individual turns."""
        turns = self.manifest.turns
        if not turns:
            return
            
        ttfas = [t.time_to_first_audio_ms for t in turns if t.time_to_first_audio_ms is not None]
        interruption_latencies = [t.interruption_stop_latency_ms for t in turns if t.interruption_stop_latency_ms is not None]

        avg_ttfa = sum(ttfas) / len(ttfas) if ttfas else None
        avg_interruption = sum(interruption_latencies) / len(interruption_latencies) if interruption_latencies else None

        evaluated = [t for t in turns if t.tool_call_correct is not None]
        tool_accuracy = (
            sum(1 for t in evaluated if t.tool_call_correct) / len(evaluated)
            if evaluated else None
        )
        hallucination_count = sum(t.hallucination_count or 0 for t in turns)

        self.manifest.metrics = AggregateMetrics(
            total_turns=len(turns),
            average_ttfa_ms=avg_ttfa,
            average_interruption_stop_latency_ms=avg_interruption,
            tool_call_accuracy_rate=tool_accuracy,
            hallucination_count=hallucination_count,
        )
