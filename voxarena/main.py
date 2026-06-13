import os
import glob
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from loguru import logger

from src.config import settings
from src.manifest import RunManifest

app = FastAPI(
    title="Voice Agent Bake-off API",
    description="Backend service for controlling runs and evaluating voice agents",
    version="1.0"
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
    return {"status": "healthy", "service": "voice-agent-bakeoff"}

@app.get("/api/config")
async def get_config():
    """Retrieve global directory settings and credentials availability (without exposing raw keys)."""
    return {
        "results_dir": settings.RESULTS_DIR,
        "script_dir": settings.SCRIPT_DIR,
        "audio_dir": settings.AUDIO_DIR,
        "review_dir": settings.REVIEW_DIR,
        "has_google_key": bool(settings.GOOGLE_API_KEY),
        "has_openai_key": bool(settings.OPENAI_API_KEY),
        "providers": ["gemini", "openai"],
        "transports": ["direct-injection", "webrtc-local"],
        "gemini_model": settings.GEMINI_MODEL,
        "openai_model": settings.OPENAI_MODEL
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

@app.on_event("startup")
async def startup_event():
    from src.database import init_db, save_run_manifest
    init_db()
    
    # Backfill runs on disk into SQLite
    manifest_files = glob.glob(os.path.join(settings.RESULTS_DIR, "**", "manifest.json"), recursive=True)
    for file_path in manifest_files:
        try:
            manifest = RunManifest.load(file_path)
            save_run_manifest(manifest)
        except Exception as e:
            logger.error(f"Failed to backfill manifest at {file_path}: {e}")

@app.get("/api/runs", response_model=List[Dict[str, Any]])
async def list_runs():
    """Retrieve all run summaries from SQLite database."""
    from src.database import list_run_summaries
    try:
        return list_run_summaries()
    except Exception as e:
        logger.error(f"Failed to list runs from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/api/runs/{run_id}", response_model=RunManifest)
async def get_run(run_id: str):
    """Retrieve details for a single run from SQLite database."""
    from src.database import load_run_manifest
    try:
        manifest = load_run_manifest(run_id)
        if manifest:
            return manifest
    except Exception as e:
        logger.error(f"Failed to load run {run_id} from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
        
    raise HTTPException(status_code=404, detail=f"Run manifest with ID {run_id} not found.")

from fastapi import BackgroundTasks
from src.agent import SaffronLeafAgent
from src.config import ProviderConfig
from src.harness import SaffronLeafBakeoffHarness

class RunRequest(BaseModel):
    provider: str
    model: str
    transport: str
    num_turns: Optional[int] = None

class CompareRunRequest(BaseModel):
    gemini_model: str
    openai_model: str
    transport: str
    num_turns: Optional[int] = None

# Keep track of active run harnesses to allow stopping them
active_harnesses: Dict[str, SaffronLeafBakeoffHarness] = {}

async def run_bakeoff_in_background(provider: str, model: str, transport: str, run_id: str, num_turns: Optional[int] = None):
    try:
        agent = SaffronLeafAgent()
        config = ProviderConfig(provider=provider, model=model, transport=transport)

        # Determine active key
        api_key = settings.GOOGLE_API_KEY if provider == "gemini" else settings.OPENAI_API_KEY
        if not api_key:
            # Fallback to dummy key if none set
            api_key = "dummy-key-for-testing"

        harness = SaffronLeafBakeoffHarness(config, agent, api_key, run_id)
        active_harnesses[run_id] = harness

        # Search for utterances in project script folder
        utterances_file = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
        await harness.run_session(utterances_file if os.path.exists(utterances_file) else None, num_turns=num_turns)
    except Exception as e:
        logger.error(f"Background run {run_id} failed: {e}")
    finally:
        active_harnesses.pop(run_id, None)

def create_pending_manifest(provider: str, model: str, transport: str, run_id: str) -> None:
    """Persist a placeholder 'pending' manifest immediately so the run is visible to clients
    before the background task has had a chance to initialize the pipeline."""
    agent = SaffronLeafAgent()
    run_dir = os.path.join(settings.RESULTS_DIR, provider, run_id)
    os.makedirs(run_dir, exist_ok=True)
    manifest = RunManifest(
        run_id=run_id,
        provider=provider,
        model=model,
        transport=transport,
        prompt_version=agent.prompt_version,
        prompt_hash=agent.prompt_hash,
        tool_schema_version=agent.tool_schema_version,
        tool_schema_hash=agent.tool_schema_hash,
        manifest_path=os.path.join(run_dir, "manifest.json"),
        status="pending"
    )
    manifest.save()

@app.post("/api/run")
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    import time
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
    """Kick off a Gemini run and an OpenAI run in parallel for side-by-side comparison."""
    import time
    base = int(time.time())
    gemini_run_id = f"run_{base}_gemini"
    openai_run_id = f"run_{base}_openai"

    create_pending_manifest("gemini", req.gemini_model, req.transport, gemini_run_id)
    create_pending_manifest("openai", req.openai_model, req.transport, openai_run_id)

    background_tasks.add_task(
        run_bakeoff_in_background, "gemini", req.gemini_model, req.transport, gemini_run_id, req.num_turns
    )
    background_tasks.add_task(
        run_bakeoff_in_background, "openai", req.openai_model, req.transport, openai_run_id, req.num_turns
    )

    return {"status": "started", "gemini_run_id": gemini_run_id, "openai_run_id": openai_run_id}

@app.post("/api/run/{run_id}/stop")
async def stop_run(run_id: str):
    harness = active_harnesses.get(run_id)
    if not harness:
        raise HTTPException(status_code=404, detail=f"Active run {run_id} not found or already completed.")
    harness.stop()
    return {"status": "stop_requested", "run_id": run_id}

@app.delete("/api/runs/{run_id}")
async def delete_run(run_id: str):
    from src.database import load_run_manifest, delete_run_from_db
    import shutil
    try:
        manifest = load_run_manifest(run_id)
    except Exception as e:
        logger.error(f"Failed to load run {run_id} from SQLite: {e}")
        raise HTTPException(status_code=500, detail=f"Database error loading run: {e}")
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Run manifest with ID {run_id} not found.")
    if run_id in active_harnesses:
        active_harnesses[run_id].stop()
        active_harnesses.pop(run_id, None)
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


from src.report_generator import generate_report

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
