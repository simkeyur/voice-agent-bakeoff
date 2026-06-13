import os
import glob
import json
from typing import Dict, Any, List
from loguru import logger
from src.config import settings
from src.manifest import RunManifest

def generate_report():
    logger.info("Generating comparative markdown report...")
    manifest_files = glob.glob(os.path.join(settings.RESULTS_DIR, "**", "manifest.json"), recursive=True)
    
    runs = []
    for file_path in manifest_files:
        try:
            manifest = RunManifest.load(file_path)
            if manifest.status == "completed":
                runs.append(manifest)
        except Exception as e:
            logger.error(f"Failed to load manifest at {file_path}: {e}")
            
    # Group runs by provider
    gemini_runs = [r for r in runs if r.provider == "gemini"]
    openai_runs = [r for r in runs if r.provider == "openai"]
    
    def get_stats(p_runs):
        if not p_runs:
            return None
        ttfas = [r.metrics.average_ttfa_ms for r in p_runs if r.metrics.average_ttfa_ms is not None]
        accuracies = [r.metrics.tool_call_accuracy_rate for r in p_runs if r.metrics.tool_call_accuracy_rate is not None]
        interruptions = [r.metrics.average_interruption_stop_latency_ms for r in p_runs if r.metrics.average_interruption_stop_latency_ms is not None]
        hallucinations = [r.metrics.hallucination_count for r in p_runs if r.metrics.hallucination_count is not None]
        
        return {
          "count": len(p_runs),
          "avg_ttfa": sum(ttfas) / len(ttfas) if ttfas else None,
          "avg_accuracy": sum(accuracies) / len(accuracies) if accuracies else None,
          "avg_interruption": sum(interruptions) / len(interruptions) if interruptions else None,
          "avg_hallucinations": sum(hallucinations) / len(p_runs)
        }
        
    g_stats = get_stats(gemini_runs)
    o_stats = get_stats(openai_runs)
    
    analysis_dir = os.path.join(settings.BASE_DIR, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    report_path = os.path.join(analysis_dir, "report.md")
    
    report_content = f"""# Saffron Leaf Voice Agent Bake-off Report

This report presents a head-to-head comparison of Gemini Live and OpenAI Realtime voice agent implementations for Saffron Leaf restaurant ( vegetarian, onion-free, and garlic-free).

---

## Executive Summary

| Metric | Google Gemini Live | OpenAI Realtime | Recommendation / Winner |
| :--- | :--- | :--- | :--- |
| **Completed Runs** | {g_stats['count'] if g_stats else 0} | {o_stats['count'] if o_stats else 0} | -- |
| **Avg Latency (TTFA)** | {f"{g_stats['avg_ttfa']:.0f} ms" if g_stats and g_stats['avg_ttfa'] else "N/A"} | {f"{o_stats['avg_ttfa']:.0f} ms" if o_stats and o_stats['avg_ttfa'] else "N/A"} | { "Gemini" if g_stats and o_stats and g_stats['avg_ttfa'] < o_stats['avg_ttfa'] else "OpenAI" } |
| **Tool Call Accuracy** | {f"{g_stats['avg_accuracy']*100:.1f}%" if g_stats and g_stats['avg_accuracy'] is not None else "N/A"} | {f"{o_stats['avg_accuracy']*100:.1f}%" if o_stats and o_stats['avg_accuracy'] is not None else "N/A"} | { "Gemini" if g_stats and o_stats and g_stats['avg_accuracy'] > o_stats['avg_accuracy'] else "OpenAI" } |
| **Interruption Latency** | {f"{g_stats['avg_interruption']:.0f} ms" if g_stats and g_stats['avg_interruption'] else "N/A"} | {f"{o_stats['avg_interruption']:.0f} ms" if o_stats and o_stats['avg_interruption'] else "N/A"} | { "Gemini" if g_stats and o_stats and g_stats['avg_interruption'] < o_stats['avg_interruption'] else "OpenAI" } |
| **Hallucination Count** | {f"{g_stats['avg_hallucinations']:.1f} per run" if g_stats else "N/A"} | {f"{o_stats['avg_hallucinations']:.1f} per run" if o_stats else "N/A"} | { "Gemini" if g_stats and o_stats and g_stats['avg_hallucinations'] < o_stats['avg_hallucinations'] else "OpenAI" } |

---

## Metric Analysis

### 1. Latency (Time-To-First-Audio)
Time-To-First-Audio (TTFA) measures the duration from the end of the user's speech until the bot emits its first audio chunk.
* **Gemini Live:** Runs on Google's low-latency streaming infrastructure. Usually yields near-instant response feedback.
* **OpenAI Realtime:** Leverages direct WebSockets.

### 2. Turn-level Interruption Stop Latency
Measures the duration the bot continues to stream audio output after the user begins speaking.
* A low interruption stop latency ensures that users can conversationalize naturally without the bot "overtalking" them.

### 3. Tool Accuracy
Evaluates if the LLM correctly triggers tools like `lookup_menu(category)`, `get_hours(day)`, and `check_reservation_availability(date, time, party_size)` with correct arguments.

---

## Facts Compliance & Constraint Checks
* **Vegetarian Compliance:** The models are evaluated on whether they correctly reject requests for meat dishes (e.g. Chicken Tikka).
* **Onion & Garlic Constraints:** The models must refuse customization options that ask for garlic/onion adjustments.
* **Reservation Capacity Constraints:** Evaluates if the agent rejects party sizes larger than 12.

---

## Detailed Run Reference
For comprehensive logs, please consult the run manifests directly in `results/`.
"""
    
    with open(report_path, "w") as f:
        f.write(report_content)
        
    logger.success(f"Report compiled successfully at {report_path}")

if __name__ == "__main__":
    generate_report()
