# Phase 4 — Developer Experience

**Target version:** v0.5  
**Impact:** Turns curious visitors into active contributors and regular users. A library lives or dies by how fast someone goes from "discovered it" to "got value from it."

---

## Problem

Right now the onboarding path is:
1. `pip install voxarena`
2. `voxarena ui`
3. Open browser, figure out API keys, figure out what templates are, run something

That's 3 steps with 0 guidance. A new user doesn't know what TTFA is, what a "template" means in this context, or what a good score looks like.

---

## What to Build

### 1. `voxarena init` wizard

```bash
$ voxarena init

Welcome to VoxArena! Let's get you set up.

? Which provider do you want to evaluate first?
  > Gemini Live
    OpenAI Realtime
    Both (side-by-side comparison)

? Paste your Gemini API key (or press Enter to skip): ****

? Which built-in scenario do you want to start with?
  > Finance / Banking (recommended)
    Restaurant Reservation
    Telecom Support
    Smart Home Control

✅ Config written to ~/.voxarena/config.toml

Run your first eval:
  voxarena run --template finance --turns 5

Or launch the UI:
  voxarena ui
```

### 2. `voxarena doctor`

Diagnoses common setup problems:

```bash
$ voxarena doctor

✅ Python 3.11+
✅ GEMINI_API_KEY set
❌ OPENAI_API_KEY not set (OpenAI runs will be unavailable)
✅ SQLite DB initialized
✅ Audio backend available
⚠️  ffmpeg not found — audio stitching will be disabled

Run `voxarena doctor --fix` to auto-install missing optional dependencies.
```

### 3. Interactive template builder

A `voxarena template new` command that walks through creating a template without touching the UI:

```bash
$ voxarena template new

? Template name: Hotel Concierge
? Describe what this agent should do: Help guests book rooms and check availability
? Paste system prompt (or 'e' to open $EDITOR): e
? Add a tool definition? (y/n): y
  Tool name: check_availability
  ...
? Add first test utterance: Hi, do you have any rooms available this weekend?

✅ Template 'hotel-concierge' created (5 utterances)
Run it: voxarena run --template hotel-concierge
```

### 4. Docs site

Current `docs/index.html` is a single page. Replace with a proper docs site (MkDocs or Docusaurus):

```
docs/
  getting-started/
    installation.md
    first-eval.md
    understanding-results.md
  guides/
    writing-templates.md
    ci-integration.md
    custom-agents.md
    custom-evaluators.md
  reference/
    cli.md
    python-api.md
    template-schema.md
    metrics-glossary.md
  examples/
```

The metrics glossary is especially important — define TTFA, tool-call accuracy, hallucination rate in plain language with examples of good/bad values.

### 5. Example gallery

`examples/` directory with runnable scripts:

```
examples/
  basic_gemini_run.py          # simplest possible eval
  side_by_side_comparison.py   # gemini vs openai on same template
  custom_agent.py              # BYO agent via BaseVoiceAgent
  ci_github_actions.yml        # copy-paste CI config
  custom_evaluator.py          # registering a custom scorer
  template_from_code.py        # defining a template in Python, not UI
```

### 6. Changelog

`CHANGELOG.md` at the repo root. Every release gets a section. Makes it easy for users to upgrade confidently and for contributors to understand what changed.

---

## Success Criteria

- A developer with no prior context can go from `pip install voxarena` to a completed eval run in under 5 minutes.
- `voxarena doctor` catches the 5 most common setup errors before the user hits them at runtime.
- The docs site has a working search and is linked from the PyPI page.
