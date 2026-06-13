import os
import json
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class TurnMetric(BaseModel):
    utterance_id: str
    text_input: str
    audio_input_path: Optional[str] = None
    transcript_output: str = ""
    audio_output_path: Optional[str] = None
    
    # Timestamps (relative or epoch milliseconds)
    input_sent_at: float
    first_audio_received_at: Optional[float] = None
    audio_completed_received_at: Optional[float] = None
    interruption_sent_at: Optional[float] = None
    interruption_stopped_at: Optional[float] = None
    
    # Latencies
    time_to_first_audio_ms: Optional[float] = None
    interruption_stop_latency_ms: Optional[float] = None
    
    # Review scores
    tool_call_correct: Optional[bool] = None
    tool_call_details: Optional[Dict[str, Any]] = None
    hallucination_count: Optional[int] = None
    evaluation_notes: Optional[str] = None
    response_match: Optional[bool] = None
    evaluation_passed: Optional[bool] = None

class AggregateMetrics(BaseModel):
    total_turns: int = 0
    average_ttfa_ms: Optional[float] = None
    average_interruption_stop_latency_ms: Optional[float] = None
    tool_call_accuracy_rate: Optional[float] = None
    hallucination_count: int = 0
    total_cost_usd: float = 0.0
    transcript_fidelity_score: Optional[float] = None  # 0 to 1 score from evaluator

class RunManifest(BaseModel):
    run_id: str
    provider: str
    model: str
    transport: str
    prompt_version: str
    prompt_hash: str
    tool_schema_version: str
    tool_schema_hash: str
    
    # Timestamps
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    
    # Status: pending, running, completed, failed
    status: str = "pending"
    error_message: Optional[str] = None
    
    # Detailed data
    turns: List[TurnMetric] = []
    metrics: AggregateMetrics = Field(default_factory=AggregateMetrics)
    
    # Path where this manifest file lives
    manifest_path: Optional[str] = None

    def save(self):
        if not self.manifest_path:
            raise ValueError("manifest_path must be set to save the manifest.")
        
        # Save JSON to disk
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, "w") as f:
            f.write(self.model_dump_json(indent=2))
            
        # Also save to SQLite DB
        try:
            from src.database import save_run_manifest
            save_run_manifest(self)
        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to save manifest to SQLite database: {e}")

    @classmethod
    def load(cls, path: str) -> "RunManifest":
        with open(path, "r") as f:
            data = json.load(f)
        manifest = cls(**data)
        manifest.manifest_path = path
        return manifest
