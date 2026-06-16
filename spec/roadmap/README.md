# VoxArena Roadmap

This folder contains the roadmap for taking VoxArena from a solid local tool to a best-in-class open source library for realtime voice agent evaluation.

## Current State (v0.1.x) — Score: 6/10

VoxArena works well as a local benchmarking UI. You can run scripted conversations against Gemini Live and OpenAI Realtime, compare TTFA and tool-call accuracy side by side, and manage test templates. The foundation is solid.

## Target State (v1.0) — Score: 10/10

A drop-in evaluation library: `pip install voxarena`, bring your own voice agent, run evals in CI, get structured results. The UI remains useful for exploration but is no longer required to get value.

---

## Roadmap Index

| Phase | Theme | Files |
|-------|-------|-------|
| Phase 1 | Headless CLI & CI mode | [01-headless-cli.md](01-headless-cli.md) |
| Phase 2 | Pluggable agent protocol | [02-pluggable-agents.md](02-pluggable-agents.md) |
| Phase 3 | Evaluation depth | [03-evaluation-depth.md](03-evaluation-depth.md) |
| Phase 4 | Developer experience | [04-developer-experience.md](04-developer-experience.md) |
| Phase 5 | Ecosystem & community | [05-ecosystem-community.md](05-ecosystem-community.md) |
