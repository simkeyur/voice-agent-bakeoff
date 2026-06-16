# Phase 5 — Ecosystem & Community

**Target version:** v1.0  
**Impact:** The difference between a library people use and a library people contribute to. At this stage VoxArena becomes a reference point in the voice agent space, not just a tool.

---

## Problem

Good open source libraries create a gravity well — contributors add providers, evaluators, and templates; companies reference it in blog posts; it shows up in "how do I evaluate my voice agent?" searches. That doesn't happen by accident.

---

## What to Build

### 1. Provider adapter library

Ship official adapters for the major voice platforms as separate installable packages:

```
voxarena-gemini        # already built-in, extracted as a reference adapter
voxarena-openai        # already built-in, extracted
voxarena-elevenlabs    # ElevenLabs Conversational AI
voxarena-hume          # Hume AI EVI
voxarena-deepgram      # Deepgram Voice Agent
voxarena-livekit       # LiveKit Agents
```

Each is a thin package that implements `BaseVoiceAgent`. The main `voxarena` package stays lean.

### 2. Template library / community hub

A curated repo (or section of the main repo) of community-contributed templates:

```
templates/
  industry/
    healthcare-triage.yaml
    insurance-claims.yaml
    e-commerce-returns.yaml
    travel-booking.yaml
  stress-tests/
    rapid-fire-questions.yaml
    context-switching.yaml
    long-session-coherence.yaml
  edge-cases/
    ambiguous-intent.yaml
    multi-language-switch.yaml
    simultaneous-tool-calls.yaml
```

Templates in YAML format so they're readable/diffable without the UI:

```yaml
id: healthcare-triage
name: Healthcare Triage
description: Patient symptom intake and appointment scheduling
system_prompt: |
  You are a healthcare triage assistant...
tools:
  - name: check_appointment_availability
    ...
utterances:
  - id: u01
    text: "Hi, I've had a headache for three days."
    expect_type: behavioral
    ...
```

### 3. Leaderboard (optional / hosted)

A public leaderboard at `voxarena.dev` (or similar) where teams can submit anonymized eval results:

- Opt-in: `voxarena run --submit-results`
- Shows aggregate p50 TTFA, tool accuracy, hallucination rate by model/version
- Automatically updates when providers ship new model versions

This is the "GitHub Stars" moment for the project — something shareable and referenceable.

### 4. `voxarena` badge

```markdown
[![VoxArena Score](https://voxarena.dev/badge/finance/gemini-3.1-flash-live-preview.svg)](https://voxarena.dev)
```

Teams add it to their README. Drives discovery.

### 5. Contribution infrastructure

- `CONTRIBUTING.md` — how to add a provider adapter, a template, an evaluator
- `ARCHITECTURE.md` — system diagram, data flow, where to find what
- Issue templates — bug report, feature request, new provider request, new template submission
- GitHub Actions: `lint`, `typecheck`, `test`, `eval-smoke-test` (runs dryrun template on each PR)
- Discord or GitHub Discussions for community questions

### 6. Published benchmarks

Quarterly blog post / notebook (e.g. on HuggingFace or a project blog):

> "VoxArena Realtime Voice Benchmark Q3 2026 — Gemini 3.1 vs OpenAI Realtime vs ElevenLabs"

Reproducible with `voxarena run` commands. Drives search traffic and establishes credibility.

---

## What "10/10" looks like

| Dimension | 10/10 State |
|-----------|------------|
| Ease of use | `pip install voxarena && voxarena run` works in 2 minutes |
| Extensibility | Any voice agent, any evaluator, any metric |
| CI integration | Drop-in GitHub Action, exit-code-based pass/fail |
| Evaluation depth | Tool accuracy (args), latency p95, barge-in, coherence |
| Community | 5+ provider adapters, 20+ community templates |
| Credibility | Referenced in voice AI blog posts and papers |
| Docs | Complete reference + guides + examples |

---

## Success Criteria

- VoxArena is the first result when someone searches "how to evaluate realtime voice agents."
- At least 3 non-Gemini/OpenAI provider adapters exist (community or official).
- A team at a company has blogged about using VoxArena in their CI pipeline.
- The leaderboard has at least 100 submitted results.
