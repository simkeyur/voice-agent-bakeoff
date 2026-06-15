"""VoxArena command-line interface.

Headless entry point for pipeline integration. Runs scripted voice-agent
evaluations against one or more providers and exits 0/1 based on whether
metrics meet the requested thresholds.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, ElementTree, SubElement


def _apply_workdir(workdir: Optional[str]) -> None:
    """Override BASE_DIR before voxarena.config is imported.

    voxarena.config.AppSettings reads BASE_DIR from the environment, so this
    must run before any module that imports `settings` is loaded.
    """
    if workdir:
        os.environ["BASE_DIR"] = os.path.abspath(workdir)


def _quiet_logs() -> None:
    from loguru import logger
    logger.remove()
    logger.add(sys.stderr, level="WARNING")


def _resolve_api_key(provider: str, settings) -> Optional[str]:
    from voxarena.providers import api_key_env
    from voxarena.config import get_setting
    return get_setting(api_key_env(provider))


def _resolve_model(provider: str, explicit: Optional[str], settings) -> str:
    if explicit:
        return explicit
    from voxarena.config import get_setting
    field = f"{provider.upper()}_MODEL"
    return get_setting(field) or ""


async def _run_single(
    provider: str,
    model: Optional[str],
    transport: str,
    script: Optional[str],
    num_turns: Optional[int],
    run_id_suffix: str = "",
) -> "RunManifest":  # noqa: F821
    from voxarena import runner
    from voxarena.config import settings
    from voxarena.providers import api_key_env

    # Up-front friendlier error messages than letting runner raise mid-coroutine
    if not _resolve_api_key(provider, settings):
        raise SystemExit(
            f"error: no API key for provider '{provider}'. Set {api_key_env(provider)}."
        )

    resolved_model = _resolve_model(provider, model, settings)
    script_path = _resolve_script_path(script, settings)
    utterances = _load_script_file(script_path)

    run_id = runner.new_run_id(suffix=run_id_suffix)
    return await runner.run_evaluation(
        provider, resolved_model, transport, run_id, num_turns, utterances=utterances
    )


def _resolve_script_path(explicit: Optional[str], settings) -> str:
    """Pick the script file the CLI should run: explicit flag, then JSON default, then YAML default."""
    if explicit:
        if not os.path.exists(explicit):
            raise SystemExit(f"error: script file not found: {explicit}")
        return explicit

    json_default = os.path.join(settings.SCRIPT_DIR, "utterances.json")
    yaml_default = os.path.join(settings.SCRIPT_DIR, "utterances.yaml")
    if os.path.exists(json_default):
        return json_default
    if os.path.exists(yaml_default):
        return yaml_default
    raise SystemExit(
        f"error: no script provided and no default found at {json_default} or {yaml_default}."
    )


def _load_script_file(path: str) -> List[Dict[str, Any]]:
    """Parse a JSON or YAML utterances script from disk into a list of turn dicts."""
    try:
        with open(path, "r") as f:
            if path.endswith(".json"):
                data = json.load(f)
            else:
                import yaml
                data = yaml.safe_load(f)
    except Exception as e:
        raise SystemExit(f"error: failed to parse script {path}: {e}")

    if not isinstance(data, list) or not data:
        raise SystemExit(f"error: script {path} must be a non-empty list of utterance entries.")
    return data


def _evaluate_thresholds(metrics, args) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if args.min_tool_accuracy is not None:
        actual = metrics.tool_call_accuracy_rate
        passed = actual is not None and actual >= args.min_tool_accuracy
        out.append({
            "name": "min_tool_accuracy",
            "required": args.min_tool_accuracy,
            "actual": actual,
            "passed": passed,
        })
    if args.max_hallucinations is not None:
        actual = metrics.hallucination_count
        passed = actual <= args.max_hallucinations
        out.append({
            "name": "max_hallucinations",
            "required": args.max_hallucinations,
            "actual": actual,
            "passed": passed,
        })
    if args.max_avg_ttfa_ms is not None:
        actual = metrics.average_ttfa_ms
        passed = actual is not None and actual <= args.max_avg_ttfa_ms
        out.append({
            "name": "max_avg_ttfa_ms",
            "required": args.max_avg_ttfa_ms,
            "actual": actual,
            "passed": passed,
        })
    return out


def _build_run_summary(manifest, thresholds: list[dict[str, Any]]) -> dict[str, Any]:
    m = manifest.metrics
    passed = manifest.status == "completed" and all(t["passed"] for t in thresholds)
    return {
        "run_id": manifest.run_id,
        "provider": manifest.provider,
        "model": manifest.model,
        "status": manifest.status,
        "metrics": {
            "total_turns": m.total_turns,
            "average_ttfa_ms": m.average_ttfa_ms,
            "average_interruption_stop_latency_ms": m.average_interruption_stop_latency_ms,
            "tool_call_accuracy_rate": m.tool_call_accuracy_rate,
            "hallucination_count": m.hallucination_count,
        },
        "thresholds": thresholds,
        "passed": passed,
        "manifest_path": manifest.manifest_path,
    }


def _write_output(payload: dict[str, Any], output_path: Optional[str]) -> None:
    text = json.dumps(payload, indent=2)
    if output_path:
        with open(output_path, "w") as f:
            f.write(text)
    else:
        print(text)


def _write_junit(summaries: list[dict[str, Any]], path: str) -> None:
    root = Element("testsuites")
    for s in summaries:
        thresholds = s["thresholds"]
        tests = thresholds or [{"name": "run_completed", "passed": s["status"] == "completed",
                                "required": "completed", "actual": s["status"]}]
        failures = sum(1 for t in tests if not t["passed"])
        suite = SubElement(root, "testsuite", {
            "name": f"voxarena.{s['provider']}",
            "tests": str(len(tests)),
            "failures": str(failures),
        })
        for t in tests:
            case = SubElement(suite, "testcase", {
                "name": t["name"],
                "classname": f"voxarena.{s['provider']}",
            })
            if not t["passed"]:
                SubElement(case, "failure", {
                    "message": f"required {t['required']}, got {t['actual']}",
                })
    ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def cmd_run(args) -> int:
    _apply_workdir(args.workdir)
    if args.quiet:
        _quiet_logs()

    manifest = asyncio.run(_run_single(
        provider=args.provider,
        model=args.model,
        transport=args.transport,
        script=args.script,
        num_turns=args.num_turns,
    ))
    thresholds = _evaluate_thresholds(manifest.metrics, args)
    summary = _build_run_summary(manifest, thresholds)

    _write_output(summary, args.output)
    if args.junit:
        _write_junit([summary], args.junit)

    return 0 if summary["passed"] else 1


def _parse_model_overrides(overrides: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in overrides:
        if "=" not in spec:
            raise SystemExit(f"error: --model expects PROVIDER=MODEL, got '{spec}'")
        provider, model = spec.split("=", 1)
        out[provider.strip()] = model.strip()
    return out


def cmd_compare(args) -> int:
    _apply_workdir(args.workdir)
    if args.quiet:
        _quiet_logs()

    from voxarena.providers import provider_names
    providers = [p.strip() for p in (args.providers or "").split(",") if p.strip()]
    if len(providers) < 2:
        raise SystemExit("error: --providers needs at least two comma-separated names")
    registered = set(provider_names())
    unknown = [p for p in providers if p not in registered]
    if unknown:
        raise SystemExit(f"error: unknown provider(s) {unknown}. Registered: {sorted(registered)}")

    model_overrides = _parse_model_overrides(args.model)

    async def _gather():
        return await asyncio.gather(*[
            _run_single(p, model_overrides.get(p), args.transport,
                        args.script, args.num_turns, run_id_suffix=f"_{p}")
            for p in providers
        ])

    manifests = asyncio.run(_gather())
    summaries = [
        _build_run_summary(m, _evaluate_thresholds(m.metrics, args))
        for m in manifests
    ]
    all_passed = all(s["passed"] for s in summaries)
    payload = {"passed": all_passed, "runs": summaries}

    _write_output(payload, args.output)
    if args.junit:
        _write_junit(summaries, args.junit)

    return 0 if all_passed else 1


def cmd_report(args) -> int:
    _apply_workdir(args.workdir)
    if args.quiet:
        _quiet_logs()

    from voxarena.report_generator import generate_report
    generate_report()
    return 0


def cmd_ui(args) -> int:
    _apply_workdir(args.workdir)
    import uvicorn
    import webbrowser
    import threading

    port = args.port
    host = args.host
    url = f"http://{host}:{port}"
    print(f"Starting VoxArena web UI server at {url}...")

    def open_browser():
        time.sleep(1.0)
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Warning: could not open browser automatically: {e}")

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("voxarena.main:app", host=host, port=port, log_level="info")
    return 0


CONFIGURABLE_KEYS = [
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_MODEL",
    "OPENAI_MODEL",
    "GEMINI_EVAL_MODEL",
    "OPENAI_EVAL_MODEL",
    "TTS_ENGINE",
    "OPENAI_TTS_MODEL",
    "OPENAI_TTS_VOICE",
    "GOOGLE_TTS_VOICE",
]

SECRET_KEYS = {"GOOGLE_API_KEY", "OPENAI_API_KEY"}


def cmd_config(args) -> int:
    """Get / set / list VoxArena settings from the CLI."""
    _apply_workdir(args.workdir)
    from voxarena.config import get_setting, set_setting, settings

    action = args.action

    if action == "list":
        rows = []
        for key in CONFIGURABLE_KEYS:
            value = get_setting(key) or getattr(settings, key, None) or ""
            if key in SECRET_KEYS and value:
                value = value[:4] + "…" + value[-4:] if len(value) > 8 else "••••"
            rows.append((key, value))
        width = max(len(k) for k, _ in rows)
        for k, v in rows:
            print(f"{k.ljust(width)}  {v}")
        return 0

    if action == "get":
        if not args.key:
            print("error: `config get` requires KEY", file=sys.stderr)
            return 2
        key = args.key.upper()
        value = get_setting(key) or getattr(settings, key, None) or ""
        if key in SECRET_KEYS and value:
            value = value[:4] + "…" + value[-4:] if len(value) > 8 else "••••"
        print(value)
        return 0

    if action == "set":
        if not args.key or args.value is None:
            print("error: `config set` requires KEY VALUE", file=sys.stderr)
            return 2
        key = args.key.upper()
        if key not in CONFIGURABLE_KEYS:
            print(
                f"error: '{key}' is not a configurable key. Known keys:\n  "
                + "\n  ".join(CONFIGURABLE_KEYS),
                file=sys.stderr,
            )
            return 2
        if key == "TTS_ENGINE" and args.value not in ("auto", "openai", "google", "local"):
            print(
                f"error: TTS_ENGINE must be one of: auto, openai, google, local (got '{args.value}')",
                file=sys.stderr,
            )
            return 2
        set_setting(key, args.value)
        display = args.value
        if key in SECRET_KEYS:
            display = "•••• (saved)"
        print(f"{key} = {display}")
        return 0

    print(f"error: unknown config action '{action}'", file=sys.stderr)
    return 2


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--transport", default="direct-injection",
                        choices=["direct-injection", "webrtc-local"])
    parser.add_argument("--script", default=None,
                        help="Path to JSON or YAML utterances script (default: <workdir>/script/utterances.json or utterances.yaml).")
    parser.add_argument("--num-turns", type=int, default=None,
                        help="Limit to the first N utterances from the script.")
    parser.add_argument("--workdir", default=None,
                        help="Project workdir containing script/ and results/ (default: cwd).")
    parser.add_argument("--output", default=None,
                        help="Write JSON result to this path (default: stdout).")
    parser.add_argument("--junit", default=None,
                        help="Write JUnit XML report to this path for CI consumption.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress non-warning logs from the harness.")
    parser.add_argument("--min-tool-accuracy", type=float, default=None,
                        help="Fail (exit 1) if tool-call accuracy is below this (0.0 - 1.0).")
    parser.add_argument("--max-hallucinations", type=int, default=None,
                        help="Fail (exit 1) if more than this many hallucinations are detected.")
    parser.add_argument("--max-avg-ttfa-ms", type=float, default=None,
                        help="Fail (exit 1) if average time-to-first-audio exceeds this (ms).")


def build_parser() -> argparse.ArgumentParser:
    # Lazy import so --help doesn't pay the full provider/Pipecat import cost
    from voxarena.providers import provider_names
    providers = provider_names()
    default_compare = ",".join(providers[:2]) if len(providers) >= 2 else providers[0] if providers else ""

    parser = argparse.ArgumentParser(
        prog="voxarena",
        description="An evaluation arena for realtime voice agents.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a scripted evaluation against one provider.")
    run.add_argument("--provider", required=True, choices=providers)
    run.add_argument("--model", default=None,
                     help="Model id (defaults to <PROVIDER>_MODEL env, e.g. GEMINI_MODEL).")
    _add_run_args(run)
    run.set_defaults(func=cmd_run)

    cmp = sub.add_parser("compare",
                         help="Run multiple providers in parallel for side-by-side comparison.")
    cmp.add_argument("--providers", default=default_compare,
                     help=f"Comma-separated providers to compare (default: {default_compare}).")
    cmp.add_argument("--model", action="append", default=[], metavar="PROVIDER=MODEL",
                     help="Override the model for one provider, e.g. --model gemini=gemini-3.1-flash-live-preview. Repeatable.")
    _add_run_args(cmp)
    cmp.set_defaults(func=cmd_compare)

    rep = sub.add_parser("report",
                         help="Generate a markdown comparison report from past runs.")
    rep.add_argument("--workdir", default=None,
                     help="Project workdir to read results/ from (default: cwd).")
    rep.add_argument("--quiet", action="store_true")
    rep.set_defaults(func=cmd_report)

    ui = sub.add_parser("ui",
                        help="Start the web control panel UI server.")
    ui.add_argument("--port", type=int, default=8000,
                    help="Port to run the UI server on (default: 8000).")
    ui.add_argument("--host", default="127.0.0.1",
                    help="Host address to bind the UI server to (default: 127.0.0.1).")
    ui.add_argument("--workdir", default=None,
                    help="Project workdir containing script/ and results/ (default: cwd).")
    ui.set_defaults(func=cmd_ui)

    cfg = sub.add_parser("config",
                         help="View or modify VoxArena settings (API keys, models, TTS).")
    cfg.add_argument("--workdir", default=None,
                     help="Project workdir containing the settings DB (default: cwd).")
    cfg_sub = cfg.add_subparsers(dest="action", required=True)

    cfg_list = cfg_sub.add_parser("list", help="Print every configurable key and its current value.")
    cfg_list.set_defaults(func=cmd_config)

    cfg_get = cfg_sub.add_parser("get", help="Print the value of one setting.")
    cfg_get.add_argument("key", help=f"One of: {', '.join(CONFIGURABLE_KEYS)}")
    cfg_get.set_defaults(func=cmd_config)

    cfg_set = cfg_sub.add_parser("set", help="Write a setting to the local SQLite settings table.")
    cfg_set.add_argument("key", help=f"One of: {', '.join(CONFIGURABLE_KEYS)}")
    cfg_set.add_argument("value", help="The new value.")
    cfg_set.set_defaults(func=cmd_config)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
