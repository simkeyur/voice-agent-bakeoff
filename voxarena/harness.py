import os
import time
import yaml
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

from src.agent import SaffronLeafAgent
from src.config import ProviderConfig, settings
from src.manifest import RunManifest, TurnMetric, AggregateMetrics
from src.providers.gemini import GeminiProviderAdapter
from src.providers.openai import OpenAIProviderAdapter

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


class SaffronLeafBakeoffHarness:
    """Manages the full automated execution of the 20-utterance test suite against a provider."""
    
    def __init__(self, config: ProviderConfig, agent: SaffronLeafAgent, api_key: str, run_id: Optional[str] = None):
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
            manifest_path=manifest_path
        )
        
        # Instantiate correct Provider Adapter
        if self.config.provider == "gemini":
            self.adapter = GeminiProviderAdapter(
                self.agent, self.config, self.manifest, self.api_key
            )
        elif self.config.provider == "openai":
            self.adapter = OpenAIProviderAdapter(
                self.agent, self.config, self.manifest, self.api_key
            )
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def stop(self):
        """Request the session to stop prematurely."""
        logger.info(f"[Harness] Stop requested for run {self.run_id}")
        self.stop_requested = True
        if self.injector:
            self.injector.stop_injection()
        if hasattr(self, "adapter") and self.adapter and self.adapter.metrics_collector:
            self.adapter.metrics_collector.turn_completed_event.set()

    def create_dummy_wav(self, file_path: str, duration_sec: float = 1.0):
        """Create a silent WAV file for dry runs or when files are missing."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        sample_rate = 16000
        num_frames = int(sample_rate * duration_sec)
        silent_data = b"\x00\x00" * num_frames
        with wave.open(file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(silent_data)
        logger.info(f"[Harness] Created dummy silent WAV at {file_path}")

    async def run_session(self, utterances_file_path: Optional[str] = None, num_turns: Optional[int] = None):
        """Executes the test suite inside a single continuous Pipecat session."""
        
        # 1. Load Utterances from YAML
        utterances = []
        if utterances_file_path and os.path.exists(utterances_file_path):
            with open(utterances_file_path, "r") as f:
                utterances = yaml.safe_load(f)
        else:
            # Fallback list for dry-runs
            logger.warning("No utterances file provided or found. Using fallback dry-run script.")
            utterances = [
                {"id": "u01", "text": "Hello, what restaurant is this?", "expect": {}},
                {"id": "u02", "text": "Are you open on Tuesdays at 2 PM?", "expect": {}},
                {"id": "u03", "text": "Can I book a table for four tomorrow at seven pm?", "expect": {}},
            ]
            
        # Limit to the requested number of conversation turns
        if num_turns is not None and num_turns > 0:
            utterances = utterances[:num_turns]

        # Ensure audio files exist or create dummies for dry-run
        for utt in utterances:
            audio_path = os.path.join(settings.AUDIO_DIR, f"{utt['id']}.wav")
            if not os.path.exists(audio_path):
                self.create_dummy_wav(audio_path, duration_sec=1.5)
        
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
        self.manifest.save()
        
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
        
        try:
            # 3. Sequence Turns
            for i, utt in enumerate(utterances):
                if self.stop_requested:
                    logger.info("[Harness] Stop requested before turn injection, breaking.")
                    break
                    
                utt_id = utt["id"]
                text = utt["text"]
                logger.info(f"\n--- [Harness] Turn {i+1}/{len(utterances)}: {utt_id} - '{text}' ---")
                
                # Signal turn start to metrics and capture
                collector.on_input_injected(utt_id, text, utt.get("expect"))
                capture.start_turn(utt_id)
                
                audio_path = os.path.join(settings.AUDIO_DIR, f"{utt_id}.wav")
                
                # Inject audio file
                injection_task = asyncio.create_task(injector.inject_wav(audio_path))
                
                # Handle Interruption logic if defined (e.g. if next turn interrupts current speaking)
                # For this baseline, we wait for turn to complete normally:
                try:
                    await asyncio.wait_for(collector.turn_completed_event.wait(), timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[Harness] Timeout waiting for response completion on {utt_id}.")
                    collector.turn_completed_event.set() # force clear
                
                # Stop injection if it was still running (e.g., timed out)
                injector.stop_injection()
                await injection_task
                
                if self.stop_requested:
                    logger.info("[Harness] Stop requested during turn wait, breaking.")
                    break
                    
                # Save captured audio for the turn
                saved_audio = capture.save_turn_audio()
                if collector.current_turn:
                    collector.current_turn.audio_output_path = saved_audio

                # Score the turn against its expected tool call / response content
                collector.evaluate_turn()
                
                # Wait between turns to simulate user reflection
                await asyncio.sleep(2.0)
                
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
            if self.stop_requested:
                self.manifest.status = "failed"
                self.manifest.error_message = "Run stopped by user."
            else:
                self.manifest.status = "completed"
            
            # Calculate aggregate metrics
            self.compile_aggregates()
            self.manifest.save()
            logger.info(f"[Harness] Manifest saved to {self.manifest.manifest_path}")
            
        except Exception as e:
            logger.error(f"[Harness] Run failed with exception: {e}")
            self.manifest.status = "failed"
            self.manifest.error_message = str(e)
            self.manifest.save()
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
            total_cost_usd=0.0           # estimated cost calculation can go here
        )
