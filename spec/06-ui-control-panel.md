# UI Control Panel Spec

## Purpose

Provide a thin control panel for launching runs, inspecting results, and comparing providers without turning the project into a product UI.

## UI Principles

- Minimal black-and-white visual system.
- Dense information, low decoration.
- Fast to scan, easy to compare, no unnecessary chrome.
- The UI is a viewer and controller for the arena, not the owner of the agent logic.

## Primary Surfaces

### Run Launcher

- Select provider.
- Select model.
- Select transport.
- Start a scripted run.
- Show run status and latest artifact path.

### Metrics Dashboard

- Show one chart per key metric: time-to-first-audio, interruption stop latency, tool-call accuracy, transcript fidelity, hallucination count, and cost per conversation.
- Support provider-by-provider comparison in the same view.
- Highlight the run-to-run spread across repeated runs.

### Results Browser

- List runs by provider, model, date, and status.
- Open raw logs and scored outputs.
- Show links to report artifacts.

## Visual Design

- Background: white or near-white.
- Text: black and grayscale only.
- Accents: use a single neutral highlight sparingly for selection or focus states.
- Typography: crisp, utilitarian, and compact.
- Layout: strong grid, clear spacing, no ornamental panels.
- Charts: simple line, bar, or dot charts with monochrome styling and direct labels.

## Metrics View Rules

- Prefer small multiples or one compact comparison chart per metric.
- Keep the chart legend minimal and label series directly when possible.
- Show both per-run values and aggregated summaries.
- Make provider comparison obvious at a glance.
- Avoid animation that obscures the comparison.

## Interaction Rules

- The panel must never mutate evaluation data.
- Launching a run should write a manifest and then stream status.
- Viewing results should be read-only.
- Any UI action must map cleanly back to a core CLI or API operation.

## Build Constraint

If the control panel is implemented later, it should sit on top of the existing provider contract and run manifest, not replace them.