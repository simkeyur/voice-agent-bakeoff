import os
import sqlite3
import json
from typing import List, Dict, Any, Optional
from loguru import logger
from src.config import settings
from src.manifest import RunManifest, TurnMetric, AggregateMetrics

DB_PATH = os.path.join(settings.RESULTS_DIR, "runs.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database and create tables if they do not exist."""
    logger.info(f"Initializing SQLite database at {DB_PATH}")
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        
        # Create runs table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                transport TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                prompt_hash TEXT NOT NULL,
                tool_schema_version TEXT NOT NULL,
                tool_schema_hash TEXT NOT NULL,
                created_at REAL NOT NULL,
                completed_at REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                metrics TEXT
            );
        """)
        
        # Create turns table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                utterance_id TEXT NOT NULL,
                text_input TEXT NOT NULL,
                audio_input_path TEXT,
                transcript_output TEXT NOT NULL,
                audio_output_path TEXT,
                input_sent_at REAL NOT NULL,
                first_audio_received_at REAL,
                audio_completed_received_at REAL,
                interruption_sent_at REAL,
                interruption_stopped_at REAL,
                time_to_first_audio_ms REAL,
                interruption_stop_latency_ms REAL,
                tool_call_correct INTEGER,
                tool_call_details TEXT,
                hallucination_count INTEGER,
                evaluation_notes TEXT,
                response_match INTEGER,
                evaluation_passed INTEGER,
                FOREIGN KEY (run_id) REFERENCES runs (run_id) ON DELETE CASCADE
            );
        """)

        # Migrate older databases that predate these columns
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(turns);").fetchall()}
        if "response_match" not in existing_cols:
            conn.execute("ALTER TABLE turns ADD COLUMN response_match INTEGER;")
        if "evaluation_passed" not in existing_cols:
            conn.execute("ALTER TABLE turns ADD COLUMN evaluation_passed INTEGER;")

        conn.commit()
    logger.success("SQLite database initialized successfully.")

def save_run_manifest(manifest: RunManifest):
    """Save or update a RunManifest in SQLite."""
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        
        # Insert or update run
        metrics_json = json.dumps(manifest.metrics.model_dump()) if manifest.metrics else None
        conn.execute("""
            INSERT INTO runs (
                run_id, provider, model, transport, prompt_version, prompt_hash,
                tool_schema_version, tool_schema_hash, created_at, completed_at,
                status, error_message, metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                completed_at = excluded.completed_at,
                status = excluded.status,
                error_message = excluded.error_message,
                metrics = excluded.metrics;
        """, (
            manifest.run_id, manifest.provider, manifest.model, manifest.transport,
            manifest.prompt_version, manifest.prompt_hash, manifest.tool_schema_version,
            manifest.tool_schema_hash, manifest.created_at, manifest.completed_at,
            manifest.status, manifest.error_message, metrics_json
        ))
        
        # For turns, we delete and re-insert
        conn.execute("DELETE FROM turns WHERE run_id = ?;", (manifest.run_id,))
        
        for turn in manifest.turns:
            tool_correct = 1 if turn.tool_call_correct is True else (0 if turn.tool_call_correct is False else None)
            tool_details = json.dumps(turn.tool_call_details) if turn.tool_call_details else None
            response_match = 1 if turn.response_match is True else (0 if turn.response_match is False else None)
            evaluation_passed = 1 if turn.evaluation_passed is True else (0 if turn.evaluation_passed is False else None)

            conn.execute("""
                INSERT INTO turns (
                    run_id, utterance_id, text_input, audio_input_path, transcript_output,
                    audio_output_path, input_sent_at, first_audio_received_at,
                    audio_completed_received_at, interruption_sent_at, interruption_stopped_at,
                    time_to_first_audio_ms, interruption_stop_latency_ms, tool_call_correct,
                    tool_call_details, hallucination_count, evaluation_notes,
                    response_match, evaluation_passed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                manifest.run_id, turn.utterance_id, turn.text_input, turn.audio_input_path,
                turn.transcript_output, turn.audio_output_path, turn.input_sent_at,
                turn.first_audio_received_at, turn.audio_completed_received_at,
                turn.interruption_sent_at, turn.interruption_stopped_at,
                turn.time_to_first_audio_ms, turn.interruption_stop_latency_ms,
                tool_correct, tool_details, turn.hallucination_count, turn.evaluation_notes,
                response_match, evaluation_passed
            ))
        conn.commit()
    logger.debug(f"Saved run manifest {manifest.run_id} to SQLite database.")

def load_run_manifest(run_id: str) -> Optional[RunManifest]:
    """Load a RunManifest by ID from SQLite."""
    with get_db_connection() as conn:
        run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?;", (run_id,)).fetchone()
        if not run_row:
            return None
            
        turn_rows = conn.execute("SELECT * FROM turns WHERE run_id = ? ORDER BY id ASC;", (run_id,)).fetchall()
        
        turns = []
        for row in turn_rows:
            tool_correct = None
            if row["tool_call_correct"] is not None:
                tool_correct = bool(row["tool_call_correct"])
                
            tool_details = None
            if row["tool_call_details"]:
                try:
                    tool_details = json.loads(row["tool_call_details"])
                except Exception:
                    pass

            response_match = None
            if row["response_match"] is not None:
                response_match = bool(row["response_match"])

            evaluation_passed = None
            if row["evaluation_passed"] is not None:
                evaluation_passed = bool(row["evaluation_passed"])

            turns.append(TurnMetric(
                utterance_id=row["utterance_id"],
                text_input=row["text_input"],
                audio_input_path=row["audio_input_path"],
                transcript_output=row["transcript_output"],
                audio_output_path=row["audio_output_path"],
                input_sent_at=row["input_sent_at"],
                first_audio_received_at=row["first_audio_received_at"],
                audio_completed_received_at=row["audio_completed_received_at"],
                interruption_sent_at=row["interruption_sent_at"],
                interruption_stopped_at=row["interruption_stopped_at"],
                time_to_first_audio_ms=row["time_to_first_audio_ms"],
                interruption_stop_latency_ms=row["interruption_stop_latency_ms"],
                tool_call_correct=tool_correct,
                tool_call_details=tool_details,
                hallucination_count=row["hallucination_count"],
                evaluation_notes=row["evaluation_notes"],
                response_match=response_match,
                evaluation_passed=evaluation_passed
            ))
            
        metrics = AggregateMetrics()
        if run_row["metrics"]:
            try:
                metrics = AggregateMetrics(**json.loads(run_row["metrics"]))
            except Exception:
                pass
                
        manifest = RunManifest(
            run_id=run_row["run_id"],
            provider=run_row["provider"],
            model=run_row["model"],
            transport=run_row["transport"],
            prompt_version=run_row["prompt_version"],
            prompt_hash=run_row["prompt_hash"],
            tool_schema_version=run_row["tool_schema_version"],
            tool_schema_hash=run_row["tool_schema_hash"],
            created_at=run_row["created_at"],
            completed_at=run_row["completed_at"],
            status=run_row["status"],
            error_message=run_row["error_message"],
            turns=turns,
            metrics=metrics
        )
        manifest.manifest_path = os.path.join(settings.RESULTS_DIR, run_row["provider"], run_id, "manifest.json")
        return manifest

def list_run_summaries() -> List[Dict[str, Any]]:
    """List summary details of all runs in SQLite."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC;").fetchall()
        runs = []
        for row in rows:
            metrics_dict = None
            if row["metrics"]:
                try:
                    metrics_dict = json.loads(row["metrics"])
                except Exception:
                    pass
            
            # Count turns
            turn_count = conn.execute("SELECT COUNT(*) FROM turns WHERE run_id = ?;", (row["run_id"],)).fetchone()[0]
            
            runs.append({
                "run_id": row["run_id"],
                "provider": row["provider"],
                "model": row["model"],
                "transport": row["transport"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "status": row["status"],
                "total_turns": turn_count,
                "aggregate_metrics": metrics_dict
            })
        return runs

def delete_run_from_db(run_id: str):
    """Delete a run and cascade delete turns from SQLite."""
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM runs WHERE run_id = ?;", (run_id,))
        conn.commit()
    logger.info(f"Deleted run {run_id} from SQLite database.")

