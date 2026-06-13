import os
import sqlite3
import json
from typing import List, Dict, Any, Optional
from loguru import logger
from voxarena.config import settings
from voxarena.manifest import RunManifest, TurnMetric, AggregateMetrics

DB_PATH = os.path.join(settings.RESULTS_DIR, "runs.db")

_INITIALIZED = False


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_initialized() -> None:
    """Lazy init for callers that don't go through the FastAPI lifespan (e.g. the CLI)."""
    global _INITIALIZED
    if not _INITIALIZED:
        init_db()
        _INITIALIZED = True

def init_db():
    """Initialize the database and create tables if they do not exist."""
    global _INITIALIZED
    logger.info(f"Initializing SQLite database at {DB_PATH}")
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        # One-shot migration: legacy turns table had an AUTOINCREMENT `id` column
        # and no composite primary key. Drop both tables so the new schema below
        # is created cleanly and the startup backfill repopulates from JSON manifests.
        try:
            legacy_cols = {row["name"] for row in conn.execute("PRAGMA table_info(turns);").fetchall()}
            if legacy_cols and "id" in legacy_cols:
                logger.warning("Detected legacy turns schema; dropping for migration to composite PK.")
                conn.execute("DROP TABLE IF EXISTS turns;")
                conn.execute("DROP TABLE IF EXISTS runs;")
                conn.commit()
        except sqlite3.OperationalError:
            pass

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

        # Create turns table — (run_id, utterance_id) is the natural identity used by UPSERT
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turns (
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
                PRIMARY KEY (run_id, utterance_id),
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
    _INITIALIZED = True
    logger.success("SQLite database initialized successfully.")

def _bool_or_none(v) -> Optional[int]:
    if v is True:
        return 1
    if v is False:
        return 0
    return None


def save_run_manifest(manifest: RunManifest):
    """Save or update a RunManifest in SQLite using per-turn UPSERT.

    Avoids the previous delete-all-then-reinsert pattern which produced O(N^2)
    writes when the harness called manifest.save() after every turn.
    """
    _ensure_initialized()
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

        # UPSERT each turn keyed by (run_id, utterance_id)
        turn_rows = [
            (
                manifest.run_id, turn.utterance_id, turn.text_input, turn.audio_input_path,
                turn.transcript_output, turn.audio_output_path, turn.input_sent_at,
                turn.first_audio_received_at, turn.audio_completed_received_at,
                turn.interruption_sent_at, turn.interruption_stopped_at,
                turn.time_to_first_audio_ms, turn.interruption_stop_latency_ms,
                _bool_or_none(turn.tool_call_correct),
                json.dumps(turn.tool_call_details) if turn.tool_call_details else None,
                turn.hallucination_count, turn.evaluation_notes,
                _bool_or_none(turn.response_match), _bool_or_none(turn.evaluation_passed),
            )
            for turn in manifest.turns
        ]

        conn.executemany("""
            INSERT INTO turns (
                run_id, utterance_id, text_input, audio_input_path, transcript_output,
                audio_output_path, input_sent_at, first_audio_received_at,
                audio_completed_received_at, interruption_sent_at, interruption_stopped_at,
                time_to_first_audio_ms, interruption_stop_latency_ms, tool_call_correct,
                tool_call_details, hallucination_count, evaluation_notes,
                response_match, evaluation_passed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, utterance_id) DO UPDATE SET
                text_input = excluded.text_input,
                audio_input_path = excluded.audio_input_path,
                transcript_output = excluded.transcript_output,
                audio_output_path = excluded.audio_output_path,
                input_sent_at = excluded.input_sent_at,
                first_audio_received_at = excluded.first_audio_received_at,
                audio_completed_received_at = excluded.audio_completed_received_at,
                interruption_sent_at = excluded.interruption_sent_at,
                interruption_stopped_at = excluded.interruption_stopped_at,
                time_to_first_audio_ms = excluded.time_to_first_audio_ms,
                interruption_stop_latency_ms = excluded.interruption_stop_latency_ms,
                tool_call_correct = excluded.tool_call_correct,
                tool_call_details = excluded.tool_call_details,
                hallucination_count = excluded.hallucination_count,
                evaluation_notes = excluded.evaluation_notes,
                response_match = excluded.response_match,
                evaluation_passed = excluded.evaluation_passed;
        """, turn_rows)
        conn.commit()
    logger.debug(f"Saved run manifest {manifest.run_id} to SQLite database.")


async def save_run_manifest_async(manifest: RunManifest) -> None:
    """Async wrapper for save_run_manifest — call from async code to keep the event loop responsive."""
    import asyncio
    await asyncio.to_thread(save_run_manifest, manifest)

def load_run_manifest(run_id: str) -> Optional[RunManifest]:
    """Load a RunManifest by ID from SQLite."""
    with get_db_connection() as conn:
        run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?;", (run_id,)).fetchone()
        if not run_row:
            return None
            
        turn_rows = conn.execute(
            "SELECT * FROM turns WHERE run_id = ? ORDER BY input_sent_at ASC;",
            (run_id,),
        ).fetchall()
        
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

def list_run_ids() -> List[str]:
    """Return all known run_ids — cheap helper for incremental backfill."""
    with get_db_connection() as conn:
        return [row["run_id"] for row in conn.execute("SELECT run_id FROM runs;").fetchall()]


def delete_run_from_db(run_id: str):
    """Delete a run and cascade delete turns from SQLite."""
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM runs WHERE run_id = ?;", (run_id,))
        conn.commit()
    logger.info(f"Deleted run {run_id} from SQLite database.")


def reset_db():
    """Wipe all runs and turns from SQLite, starting from a clean slate."""
    _ensure_initialized()
    with get_db_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM turns;")
        conn.execute("DELETE FROM runs;")
        conn.commit()
    logger.warning("Reset SQLite database: deleted all runs and turns.")

