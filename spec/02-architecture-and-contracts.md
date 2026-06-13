# Architecture and Contracts

## Architecture

```text
recorded WAVs -> injection harness -> Pipecat pipeline -> provider backend
                                         |
                              timing + transcript logger
                                         |
                               results/runs/{provider}/{run}/
                                         |
                             sub-agent reviewers (Claude API)
                                         |
                                   analysis/report.md
```

## Provider Boundary

One provider interface should sit between the agent and the vendor SDKs. The agent must not know which vendor is active.

Core provider-facing operations:

- Create a realtime session.
- Stream audio in and audio out.
- Emit tool calls using a shared schema.
- Report usage, latency, and metadata in a normalized run record.

Recommended config shape:

- `provider`: `gemini`, `openai`, or future providers.
- `model`: concrete model name/version.
- `transport`: `direct-injection` or `webrtc-local`.
- `run_id`: unique identifier for all emitted artifacts.
- `prompt_version` and `tool_schema_version`: pinned identifiers for reproducibility.

## Run Manifest

Every run should emit a manifest with at least:

- provider
- model
- version
- prompt hash
- tool schema hash
- transport settings
- run id
- timestamps

## Repo Structure

```text
voxarena/
├── claude.md
├── spec/
├── pyproject.toml
├── .env.example
├── voxarena/
│   ├── agent.py
│   ├── providers/
│   │   ├── base.py
│   │   ├── gemini.py
│   │   └── openai.py
│   ├── tools.py
│   ├── harness.py
│   └── metrics.py
├── script/
│   ├── utterances.yaml
│   └── audio/
├── review/
└── results/
```

## Layout Rule

Keep provider-specific code isolated in adapters. Do not let vendor branches spread through the agent or harness.
