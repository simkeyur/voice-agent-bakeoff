"""Shared run orchestration used by both the CLI and the FastAPI backend.

This module owns the canonical answer to "how do you run one evaluation":
resolve the API key, build the agent + config + harness, drive the scripted
session, and update the persisted manifest on failure. Both ``voxarena.cli``
and ``voxarena.main`` call into here so the run semantics are identical
across surfaces.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, Optional

from loguru import logger

from voxarena.agent import Agent
from voxarena.config import ProviderConfig, settings
from voxarena.harness import EvaluationHarness
from voxarena.manifest import RunManifest
from voxarena.providers import api_key_env


# Run id -> live harness, so the HTTP layer can stop in-flight runs.
ACTIVE_HARNESSES: Dict[str, EvaluationHarness] = {}


def resolve_api_key(provider: str) -> Optional[str]:
    """Look up the API key for a provider from the environment / settings."""
    env_name = api_key_env(provider)
    return os.environ.get(env_name) or getattr(settings, env_name, None)


def default_model_for(provider: str) -> str:
    """Look up the default model env var for a provider (e.g. GEMINI_MODEL)."""
    field = f"{provider.upper()}_MODEL"
    return getattr(settings, field, None) or ""


def new_run_id(suffix: str = "") -> str:
    """Generate a fresh run id with an optional suffix (used by ``compare``)."""
    return f"run_{int(time.time())}{suffix}"


def create_pending_manifest(provider: str, model: str, transport: str, run_id: str) -> RunManifest:
    """Write a placeholder ``status: pending`` manifest before the run starts.

    Lets HTTP clients see the run immediately, before the background task has
    booted the Pipecat session.
    """
    agent = Agent()
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
        status="pending",
    )
    manifest.save()
    return manifest


async def run_evaluation(
    provider: str,
    model: str,
    transport: str,
    run_id: str,
    num_turns: Optional[int] = None,
    script: Optional[str | List[Dict[str, Any]]] = None,
) -> RunManifest:
    """Drive a single scripted evaluation end-to-end and return the final manifest.

    The harness writes its own manifest to disk; on uncaught failure we mark the
    manifest as ``failed`` so callers (and the UI) can see the error. Stopping
    is supported via :func:`stop_run` by run_id.
    """
    try:
        api_key = resolve_api_key(provider)
        if not api_key:
            raise RuntimeError(
                f"No API key configured for provider '{provider}' (set {api_key_env(provider)})."
            )

        config = ProviderConfig(provider=provider, model=model, transport=transport)
        agent = Agent()
        harness = EvaluationHarness(config, agent, api_key, run_id)
        ACTIVE_HARNESSES[run_id] = harness

        await harness.run_session(
            script,
            num_turns=num_turns,
        )
        return RunManifest.load(harness.manifest.manifest_path)
    except Exception as e:
        logger.error(f"Run {run_id} failed: {e}")
        _mark_manifest_failed(provider, run_id, str(e))
        raise
    finally:
        ACTIVE_HARNESSES.pop(run_id, None)


async def run_evaluations_parallel(
    specs: list[tuple[str, str, str, str, Optional[int]]],
    script: Optional[str | List[Dict[str, Any]]] = None,
) -> list[RunManifest]:
    """Run multiple ``(provider, model, transport, run_id, num_turns)`` specs in parallel."""
    return await asyncio.gather(*[
        run_evaluation(p, m, t, rid, n, script) for p, m, t, rid, n in specs
    ])


def stop_run(run_id: str) -> bool:
    """Request stop for an in-flight run. Returns True if the run was active."""
    harness = ACTIVE_HARNESSES.get(run_id)
    if not harness:
        return False
    harness.stop()
    return True


def _mark_manifest_failed(provider: str, run_id: str, error_message: str) -> None:
    """Best-effort: persist a failure status to the manifest if it exists on disk."""
    try:
        manifest_path = os.path.join(settings.RESULTS_DIR, provider, run_id, "manifest.json")
        if os.path.exists(manifest_path):
            m = RunManifest.load(manifest_path)
            m.status = "failed"
            m.error_message = error_message
            m.save()
    except Exception as save_err:
        logger.error(f"Failed to persist failure for run {run_id}: {save_err}")
