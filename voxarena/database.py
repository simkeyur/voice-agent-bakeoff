import asyncio
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
    # WAL + relaxed sync give us concurrent reads/writes without "database is
    # locked" errors under parallel compare runs. Foreign keys must be enabled
    # per-connection in SQLite.
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_initialized() -> None:
    """Lazy init for callers that don't go through the FastAPI lifespan (e.g. the CLI)."""
    if not _INITIALIZED:
        init_db()


def init_db():
    """Initialize the database and create tables if they do not exist."""
    global _INITIALIZED
    logger.info(f"Initializing SQLite database at {DB_PATH}")
    with get_db_connection() as conn:
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

        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(turns);").fetchall()}
        if "response_match" not in existing_cols:
            conn.execute("ALTER TABLE turns ADD COLUMN response_match INTEGER;")
        if "evaluation_passed" not in existing_cols:
            conn.execute("ALTER TABLE turns ADD COLUMN evaluation_passed INTEGER;")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS utterances (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                expect TEXT,
                position INTEGER NOT NULL DEFAULT 0
            );
        """)

        # Migrate older databases that predate the position column. Backfill
        # positions by current rowid so existing rows keep their relative order.
        utt_cols = {row["name"] for row in conn.execute("PRAGMA table_info(utterances);").fetchall()}
        if "position" not in utt_cols:
            conn.execute("ALTER TABLE utterances ADD COLUMN position INTEGER NOT NULL DEFAULT 0;")
            conn.execute(
                "UPDATE utterances SET position = (SELECT COUNT(*) FROM utterances u2 WHERE u2.rowid <= utterances.rowid);"
            )

        conn.commit()
    _INITIALIZED = True
    logger.success("SQLite database initialized successfully.")


def _bool_or_none(v) -> Optional[int]:
    if v is True:
        return 1
    if v is False:
        return 0
    return None


_RUN_UPSERT_SQL = """
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
"""

_TURN_UPSERT_SQL = """
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
"""


def _run_row(manifest: RunManifest) -> tuple:
    metrics_json = json.dumps(manifest.metrics.model_dump()) if manifest.metrics else None
    return (
        manifest.run_id, manifest.provider, manifest.model, manifest.transport,
        manifest.prompt_version, manifest.prompt_hash, manifest.tool_schema_version,
        manifest.tool_schema_hash, manifest.created_at, manifest.completed_at,
        manifest.status, manifest.error_message, metrics_json,
    )


def _turn_row(run_id: str, turn: TurnMetric) -> tuple:
    return (
        run_id, turn.utterance_id, turn.text_input, turn.audio_input_path,
        turn.transcript_output, turn.audio_output_path, turn.input_sent_at,
        turn.first_audio_received_at, turn.audio_completed_received_at,
        turn.interruption_sent_at, turn.interruption_stopped_at,
        turn.time_to_first_audio_ms, turn.interruption_stop_latency_ms,
        _bool_or_none(turn.tool_call_correct),
        json.dumps(turn.tool_call_details) if turn.tool_call_details else None,
        turn.hallucination_count, turn.evaluation_notes,
        _bool_or_none(turn.response_match), _bool_or_none(turn.evaluation_passed),
    )


def save_run_manifest(manifest: RunManifest):
    """Upsert the run row plus every turn. Used for full saves (startup backfill,
    end-of-run finalization). For mid-run updates prefer save_run_progress."""
    _ensure_initialized()
    with get_db_connection() as conn:
        conn.execute(_RUN_UPSERT_SQL, _run_row(manifest))
        conn.executemany(_TURN_UPSERT_SQL, [_turn_row(manifest.run_id, t) for t in manifest.turns])
        conn.commit()
    logger.debug(f"Saved run manifest {manifest.run_id} to SQLite database.")


def save_run_progress(manifest: RunManifest, turn: Optional[TurnMetric] = None):
    """Upsert the run row plus (optionally) a single turn. Avoids the O(N^2)
    write amplification of re-upserting every turn after each step of a run."""
    _ensure_initialized()
    with get_db_connection() as conn:
        conn.execute(_RUN_UPSERT_SQL, _run_row(manifest))
        if turn is not None:
            conn.execute(_TURN_UPSERT_SQL, _turn_row(manifest.run_id, turn))
        conn.commit()


async def save_run_manifest_async(manifest: RunManifest) -> None:
    """Async wrapper for save_run_manifest — call from async code to keep the event loop responsive."""
    await asyncio.to_thread(save_run_manifest, manifest)


async def save_run_progress_async(manifest: RunManifest, turn: Optional[TurnMetric] = None) -> None:
    await asyncio.to_thread(save_run_progress, manifest, turn)


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
                evaluation_passed=evaluation_passed,
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
            metrics=metrics,
        )
        manifest.manifest_path = os.path.join(settings.RESULTS_DIR, run_row["provider"], run_id, "manifest.json")
        return manifest


def list_run_summaries() -> List[Dict[str, Any]]:
    """List summary details of all runs in SQLite (single query, no N+1)."""
    with get_db_connection() as conn:
        rows = conn.execute("""
            SELECT r.*, COALESCE(t.turn_count, 0) AS turn_count
            FROM runs r
            LEFT JOIN (
                SELECT run_id, COUNT(*) AS turn_count
                FROM turns GROUP BY run_id
            ) t ON r.run_id = t.run_id
            ORDER BY r.created_at DESC;
        """).fetchall()
        runs = []
        for row in rows:
            metrics_dict = None
            if row["metrics"]:
                try:
                    metrics_dict = json.loads(row["metrics"])
                except Exception:
                    pass

            runs.append({
                "run_id": row["run_id"],
                "provider": row["provider"],
                "model": row["model"],
                "transport": row["transport"],
                "created_at": row["created_at"],
                "completed_at": row["completed_at"],
                "status": row["status"],
                "total_turns": row["turn_count"],
                "aggregate_metrics": metrics_dict,
            })
        return runs


def list_run_ids() -> List[str]:
    """Return all known run_ids — cheap helper for incremental backfill."""
    with get_db_connection() as conn:
        return [row["run_id"] for row in conn.execute("SELECT run_id FROM runs;").fetchall()]


def delete_run_from_db(run_id: str):
    """Delete a run and cascade delete turns from SQLite."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM runs WHERE run_id = ?;", (run_id,))
        conn.commit()
    logger.info(f"Deleted run {run_id} from SQLite database.")


def reset_db():
    """Wipe all runs and turns from SQLite, starting from a clean slate."""
    _ensure_initialized()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM turns;")
        conn.execute("DELETE FROM runs;")
        conn.commit()
    logger.warning("Reset SQLite database: deleted all runs and turns.")


def load_utterances_from_db() -> List[Dict[str, Any]]:
    """Retrieve all conversation utterances from SQLite, preserving insertion order."""
    _ensure_initialized()
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT id, text, expect FROM utterances ORDER BY position ASC, id ASC;"
        ).fetchall()
        utterances = []
        for row in rows:
            expect = {}
            if row["expect"]:
                try:
                    expect = json.loads(row["expect"])
                except Exception:
                    pass
            utterances.append({
                "id": row["id"],
                "text": row["text"],
                "expect": expect,
            })
        return utterances


def save_utterances_to_db(utterances: List[Dict[str, Any]]) -> None:
    """Atomically replace conversation utterances in SQLite.

    Uses upsert + delete-missing so a mid-write failure can never leave the
    table empty (unlike DELETE-then-INSERT). All writes happen in a single
    transaction. Position is taken from the payload order.
    """
    _ensure_initialized()
    rows = [
        (u["id"], u["text"], json.dumps(u.get("expect") or {}), idx)
        for idx, u in enumerate(utterances)
    ]
    keep_ids = [r[0] for r in rows]

    with get_db_connection() as conn:
        conn.execute("BEGIN;")
        try:
            if rows:
                conn.executemany("""
                    INSERT INTO utterances (id, text, expect, position)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        text = excluded.text,
                        expect = excluded.expect,
                        position = excluded.position;
                """, rows)
                placeholders = ",".join("?" * len(keep_ids))
                conn.execute(
                    f"DELETE FROM utterances WHERE id NOT IN ({placeholders});",
                    keep_ids,
                )
            else:
                conn.execute("DELETE FROM utterances;")
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def bootstrap_utterances_if_empty() -> None:
    """One-time seed of the utterances table from a default YAML script or templates definition.

    Kept out of init_db so the disk read and YAML parse don't run inside schema
    setup (and don't block the FastAPI event loop during the lifespan hook).
    """
    _ensure_initialized()
    with get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM utterances;").fetchone()[0]
    if count > 0:
        return

    # Try loading from built-in python templates first
    try:
        from voxarena.templates import TEMPLATES
        save_utterances_to_db(TEMPLATES["restaurant"]["utterances"])
        logger.info("Bootstrapped 5 default utterances (Restaurant) from python templates into SQLite.")
        return
    except Exception as e:
        logger.warning(f"Failed to bootstrap utterances from python templates: {e}")

    # Fallback to YAML script if python templates failed
    import yaml
    default_yaml = None
    script_yaml = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    if os.path.exists(script_yaml):
        default_yaml = script_yaml
    else:
        try:
            import importlib.resources
            pkg_yaml = importlib.resources.files("voxarena").joinpath("default_script").joinpath("utterances.yaml")
            if pkg_yaml.exists():
                default_yaml = str(pkg_yaml)
        except Exception:
            pass

    if not default_yaml:
        return

    try:
        with open(default_yaml, "r") as f:
            parsed = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to read default utterances at {default_yaml}: {e}")
        return

    if not isinstance(parsed, list) or not parsed:
        return

    try:
        save_utterances_to_db(parsed)
        logger.info(f"Bootstrapped {len(parsed)} utterances from {default_yaml} into SQLite.")
    except Exception as e:
        logger.error(f"Failed to bootstrap database utterances: {e}")
