import os
import glob
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from loguru import logger

from voxarena.config import settings
from voxarena.manifest import RunManifest
from voxarena.providers import provider_names, api_key_env


@asynccontextmanager
async def lifespan(app: FastAPI):
    from voxarena.database import init_db, save_run_manifest, list_run_ids
    init_db()

    # Incrementally backfill any manifests that aren't yet in SQLite.
    known_ids = set(list_run_ids())
    manifest_files = glob.glob(os.path.join(settings.RESULTS_DIR, "**", "manifest.json"), recursive=True)
    for file_path in manifest_files:
        try:
            manifest = RunManifest.load(file_path)
            if manifest.run_id not in known_ids:
                save_run_manifest(manifest)
        except Exception as e:
            logger.error(f"Failed to backfill manifest at {file_path}: {e}")
    yield


app = FastAPI(
    title="VoxArena API",
    description="Backend service for controlling runs and evaluating realtime voice agents",
    version="1.0",
    lifespan=lifespan,
)

# CORS middleware for development frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all during dev; restrict in prod if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "voxarena"}

def _api_key_for(provider: str) -> Optional[str]:
    return os.environ.get(api_key_env(provider)) or getattr(settings, api_key_env(provider), None)


@app.get("/api/config")
async def get_config():
    """Retrieve global directory settings and credentials availability (without exposing raw keys)."""
    providers = provider_names()
    return {
        "base_dir": settings.BASE_DIR,
        "results_dir": settings.RESULTS_DIR,
        "script_dir": settings.SCRIPT_DIR,
        "audio_dir": settings.AUDIO_DIR,
        "review_dir": settings.REVIEW_DIR,
        "has_google_key": bool(settings.GOOGLE_API_KEY),
        "has_openai_key": bool(settings.OPENAI_API_KEY),
        "providers": providers,
        "has_api_key": {p: bool(_api_key_for(p)) for p in providers},
        "transports": ["direct-injection", "webrtc-local"],
        "gemini_model": settings.GEMINI_MODEL,
        "openai_model": settings.OPENAI_MODEL,
    }

class SettingsUpdateRequest(BaseModel):
    gemini_model: str
    openai_model: str

def _update_env_file(updates: Dict[str, str]):
    """Update or add KEY=VALUE lines in the project's .env file without touching other entries."""
    env_path = os.path.join(settings.BASE_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    remaining = dict(updates)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        for key in list(remaining.keys()):
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines[idx] = f"{key}={remaining.pop(key)}\n"
                break

    for key, value in remaining.items():
        lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

@app.get("/api/settings")
async def get_settings():
    """Retrieve editable application settings."""
    return {
        "gemini_model": settings.GEMINI_MODEL,
        "openai_model": settings.OPENAI_MODEL
    }

@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    """Update the Gemini/OpenAI model configuration, persisted to .env."""
    settings.GEMINI_MODEL = req.gemini_model
    settings.OPENAI_MODEL = req.openai_model
    _update_env_file({
        "GEMINI_MODEL": req.gemini_model,
        "OPENAI_MODEL": req.openai_model
    })
    return {"status": "saved", "gemini_model": settings.GEMINI_MODEL, "openai_model": settings.OPENAI_MODEL}

@app.get("/api/utterances")
async def get_utterances():
    """Retrieve the raw YAML content of the scripted conversation utterances."""
    utterances_path = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    if not os.path.exists(utterances_path):
        return {"content": ""}
    with open(utterances_path, "r") as f:
        return {"content": f.read()}

class UtterancesUpdateRequest(BaseModel):
    content: str

@app.post("/api/utterances")
async def update_utterances(req: UtterancesUpdateRequest):
    """Validate and persist the scripted conversation utterances YAML."""
    import yaml
    try:
        parsed = yaml.safe_load(req.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="Utterances YAML must be a list of utterance entries.")

    utterances_path = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    with open(utterances_path, "w") as f:
        f.write(req.content)

    return {"status": "saved", "count": len(parsed)}

@app.get("/api/runs", response_model=List[Dict[str, Any]])
async def list_runs():
    """Retrieve all run summaries from SQLite database."""
    from voxarena.database import list_run_summaries
    try:
        return list_run_summaries()
    except Exception as e:
        logger.error(f"Failed to list runs from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/api/runs/{run_id}", response_model=RunManifest)
async def get_run(run_id: str):
    """Retrieve details for a single run from SQLite database."""
    from voxarena.database import load_run_manifest
    try:
        manifest = load_run_manifest(run_id)
        if manifest:
            return manifest
    except Exception as e:
        logger.error(f"Failed to load run {run_id} from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    raise HTTPException(status_code=404, detail=f"Run manifest with ID {run_id} not found.")

from fastapi import BackgroundTasks
from voxarena import runner
from voxarena.runner import ACTIVE_HARNESSES, create_pending_manifest

class RunRequest(BaseModel):
    provider: str
    model: str
    transport: str
    num_turns: Optional[int] = None

class CompareRunRequest(BaseModel):
    transport: str
    num_turns: Optional[int] = None
    # New generic shape: dict of provider -> model id (None means use that provider's default)
    models: Optional[Dict[str, Optional[str]]] = None
    # Back-compat fields for the existing UI / clients
    gemini_model: Optional[str] = None
    openai_model: Optional[str] = None

async def run_bakeoff_in_background(provider: str, model: str, transport: str, run_id: str, num_turns: Optional[int] = None):
    """Thin wrapper that swallows runner.run_evaluation's exception so the
    BackgroundTask coroutine doesn't bubble an unhandled error."""
    try:
        await runner.run_evaluation(provider, model, transport, run_id, num_turns)
    except Exception:
        # runner already logged and marked the manifest as failed
        pass

def _require_api_key(provider: str) -> None:
    if not _api_key_for(provider):
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for '{provider}'. Set {api_key_env(provider)} in .env.",
        )

@app.post("/api/run")
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    import time
    _require_api_key(req.provider)
    run_id = f"run_{int(time.time())}"
    create_pending_manifest(req.provider, req.model, req.transport, run_id)
    background_tasks.add_task(
        run_bakeoff_in_background,
        req.provider,
        req.model,
        req.transport,
        run_id,
        req.num_turns
    )
    return {"status": "started", "run_id": run_id}

@app.post("/api/run/compare")
async def start_compare_run(req: CompareRunRequest, background_tasks: BackgroundTasks):
    """Kick off N provider runs in parallel for side-by-side comparison."""
    import time

    # Resolve provider -> model map. Prefer new shape; fall back to legacy fields.
    if req.models:
        models = {p: m for p, m in req.models.items()}
    else:
        models = {}
        if req.gemini_model is not None:
            models["gemini"] = req.gemini_model
        if req.openai_model is not None:
            models["openai"] = req.openai_model

    if len(models) < 2:
        raise HTTPException(status_code=400, detail="compare needs at least two providers; pass 'models' or both legacy fields.")

    registered = set(provider_names())
    unknown = [p for p in models if p not in registered]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown provider(s) {unknown}. Registered: {sorted(registered)}")

    for p in models:
        _require_api_key(p)

    base = int(time.time())
    run_ids: Dict[str, str] = {}
    for provider, model in models.items():
        resolved_model = model or getattr(settings, f"{provider.upper()}_MODEL", "")
        run_id = f"run_{base}_{provider}"
        run_ids[provider] = run_id
        create_pending_manifest(provider, resolved_model, req.transport, run_id)
        background_tasks.add_task(
            run_bakeoff_in_background, provider, resolved_model, req.transport, run_id, req.num_turns
        )

    # Return a generic mapping plus the legacy keys for clients that still expect them.
    payload: Dict[str, Any] = {"status": "started", "run_ids": run_ids}
    if "gemini" in run_ids:
        payload["gemini_run_id"] = run_ids["gemini"]
    if "openai" in run_ids:
        payload["openai_run_id"] = run_ids["openai"]
    return payload

@app.post("/api/run/{run_id}/stop")
async def stop_run(run_id: str):
    if not runner.stop_run(run_id):
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found or already completed.")
    return {"status": "stop_requested", "run_id": run_id}

@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str):
    from voxarena.database import load_run_manifest, delete_run_from_db
    import shutil
    try:
        manifest = load_run_manifest(run_id)
    except Exception as e:
        logger.error(f"Failed to load run {run_id} from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error loading run: {e}")
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Run manifest with ID {run_id} not found.")
    if run_id in ACTIVE_HARNESSES:
        runner.stop_run(run_id)
        ACTIVE_HARNESSES.pop(run_id, None)
    run_dir = os.path.join(settings.RESULTS_DIR, manifest.provider, run_id)
    if os.path.exists(run_dir):
        try:
            shutil.rmtree(run_dir)
            logger.info(f"Deleted run folder on disk: {run_dir}")
        except Exception as e:
            logger.error(f"Failed to delete run folder {run_dir}: {e}")
    try:
        delete_run_from_db(run_id)
    except Exception as e:
        logger.error(f"Failed to delete run {run_id} from SQLite DB: {e}")
        raise HTTPException(status_code=500, detail=f"Database error deleting run: {e}")
    return {"status": "deleted", "run_id": run_id}


@app.post("/api/database/reset")
async def reset_database():
    """Wipe all run history from SQLite and delete saved results/audio on disk."""
    from voxarena.database import reset_db
    import shutil

    for run_id in list(ACTIVE_HARNESSES.keys()):
        runner.stop_run(run_id)
    ACTIVE_HARNESSES.clear()

    try:
        reset_db()
    except Exception as e:
        logger.error(f"Failed to reset SQLite database: {e}")
        raise HTTPException(status_code=500, detail=f"Database error during reset: {e}")

    for provider in provider_names():
        provider_dir = os.path.join(settings.RESULTS_DIR, provider)
        if os.path.exists(provider_dir):
            try:
                shutil.rmtree(provider_dir)
                logger.info(f"Deleted results folder on disk: {provider_dir}")
            except Exception as e:
                logger.error(f"Failed to delete results folder {provider_dir}: {e}")

    return {"status": "reset"}


from voxarena.report_generator import generate_report

@app.post("/api/report")
async def compile_report():
    try:
        generate_report()
        return {"status": "compiled", "report_path": os.path.join(settings.BASE_DIR, "analysis", "report.md")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/api/results", StaticFiles(directory=settings.RESULTS_DIR), name="results")

# Serve compiled frontend static files if they exist
ui_dist_path = os.path.join(settings.BASE_DIR, "ui", "dist")
if os.path.exists(ui_dist_path):
    logger.info(f"Serving static files from {ui_dist_path}")
    app.mount("/", StaticFiles(directory=ui_dist_path, html=True), name="ui")
else:
    logger.warning(f"UI build directory not found at {ui_dist_path}. Run frontend dev server separately or build the UI.")
    @app.get("/")
    async def index_fallback():
        return {"message": "FastAPI is running. UI dist directory not found. Please build the UI."}
