<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="ui/src/assets/logo-dark.png" />
    <img src="ui/src/assets/logo.png" alt="VoxArena" width="220" />
  </picture>
</p>

<p align="center"><em>An evaluation arena for realtime voice agents.</em></p>

<p align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Built with Pipecat](https://img.shields.io/badge/built%20with-pipecat-9cf.svg)](https://github.com/pipecat-ai/pipecat)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

</p>

VoxArena is a reproducible benchmarking harness for realtime voice agents. Run the same scripted conversation across Gemini Live, OpenAI Realtime, and other [Pipecat](https://github.com/pipecat-ai/pipecat)-supported providers — and compare them apples-to-apples on latency, tool-call accuracy, and hallucinations.

Drop it into your CI pipeline, your dev loop, or the bundled control panel.

---

## 🚀 CI & Pipeline Integration

VoxArena ships a `voxarena` CLI designed for headless use in your build pipeline. It returns a non-zero exit code when metrics fall below thresholds you define, and emits JUnit XML for native CI reporting.

```bash
pip install voxarena

voxarena run \
  --provider gemini \
  --script ./script/utterances.yaml \
  --min-tool-accuracy 0.9 \
  --max-hallucinations 0 \
  --max-avg-ttfa-ms 1500 \
  --output result.json \
  --junit voxarena.xml
# exit 0 if every threshold passes, 1 otherwise
```

### Compare two providers in one shot

```bash
voxarena compare \
  --gemini-model gemini-3.1-flash-live-preview \
  --openai-model gpt-realtime-2 \
  --num-turns 5 \
  --min-tool-accuracy 0.9 \
  --output compare.json
```

### GitHub Actions

```yaml
- name: Voice agent regression check
  env:
    GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
  run: |
    pip install voxarena
    voxarena run --provider gemini \
      --min-tool-accuracy 0.92 --max-hallucinations 0 \
      --junit voxarena.xml --quiet

- uses: mikepenz/action-junit-report@v4
  if: always()
  with:
    report_paths: voxarena.xml
```

### Subcommands

| Command | What it does |
| --- | --- |
| `voxarena run` | Single-provider scripted run; exits 0/1 against thresholds. |
| `voxarena compare` | Runs Gemini and OpenAI in parallel against the same script. |
| `voxarena report` | Generates a markdown comparison report from past runs. |

Run `voxarena <command> --help` for the full flag set.

---

## Features

- 🎙️ **Provider-agnostic agent** — one Pipecat pipeline drives every provider; swap models without re-implementing your agent
- 🔁 **Scripted conversations** — multi-turn YAML scripts with pre-recorded WAV inputs and expected tool calls / response content
- 📊 **Automated scoring** — tool-call correctness, response matching, hallucination counts, time-to-first-audio, interruption-stop latency
- 🆚 **Side-by-side comparisons** — run multiple providers in parallel against the same script
- 🗄️ **Persistent run history** — JSON manifests on disk, indexed in SQLite
- 🖥️ **Web control panel** — React UI to launch runs, watch live status, browse results, and edit scripts
- 🧩 **Extensible** — add a new provider by implementing one adapter class

## Architecture

```mermaid
flowchart TD
    A["Recorded WAVs<br/>script/audio/*.wav"] --> B["Injection Harness<br/>voxarena/harness.py"]
    B --> C

    subgraph C ["Pipecat Pipeline"]
        direction LR
        C1["Audio Injector"] --> C2["Provider Adapter"]
        C2 --> C3["Audio Capture"]
        C3 --> C4["Metrics Collector"]
    end

    C2 <--> D{{"Provider Backend"}}
    D --> D1["Gemini Live"]
    D --> D2["OpenAI Realtime"]
    D --> D3["...future providers"]

    C4 --> E["Run Manifest<br/>results/PROVIDER/RUN_ID/manifest.json"]
    E --> F[("SQLite Index<br/>runs.db")]

    F <--> G["voxarena CLI<br/>+ FastAPI Backend"]
    G <--> H["React Control Panel<br/>ui/"]

    style D1 fill:#4285F4,color:#fff,stroke:#333
    style D2 fill:#10A37F,color:#fff,stroke:#333
    style D3 fill:#999,color:#fff,stroke:#333
    style F fill:#f5f5f5,stroke:#333
    style H fill:#fff7da,stroke:#333
```

## Local Dev (with UI)

```bash
git clone https://github.com/<your-org>/voxarena.git
cd voxarena
cp .env.example .env  # add GOOGLE_API_KEY / OPENAI_API_KEY

python3 -m venv .venv && source .venv/bin/activate
pip install -e .

uvicorn voxarena.main:app --reload --port 8000
```

Then in another terminal:

```bash
cd ui && npm install && npm run dev
```

Open the control panel at `http://localhost:5173`.

## Bring Your Own Agent

The demo ships with the "Saffron Leaf" restaurant agent so you can run end-to-end on day one. To evaluate your own:

1. Replace the system prompt and tool schemas in `voxarena/agent.py`
2. Implement (or stub) your tools in `voxarena/tools.py`
3. Re-record `script/audio/*.wav` and update `script/utterances.yaml` to reflect your real workload
4. Run the arena as normal — every provider gets scored against your scripts

## Scripted Conversations

Conversations live in [`script/utterances.yaml`](script/utterances.yaml). Each turn pairs an utterance id with an `expect` block describing the correct tool call and/or response content:

```yaml
- id: u04
  text: "Are you open on Sundays?"
  expect:
    tool: get_hours
    args:
      day: sunday
    response_contains:
      - "closed"
```

The harness plays `script/audio/{id}.wav` into the pipeline and scores the agent's actual tool calls and transcript against `expect`.

## Configuration

| Variable | Description |
| --- | --- |
| `GOOGLE_API_KEY` / `OPENAI_API_KEY` | Provider credentials |
| `GEMINI_MODEL` / `OPENAI_MODEL` | Realtime model under test |
| `GEMINI_EVAL_MODEL` / `OPENAI_EVAL_MODEL` | Cheaper text models for grading |
| `PORT` | FastAPI server port |
| `BASE_DIR` | Override workdir (CLI: `--workdir`) |

## Contributing

To add a new provider: implement an adapter in `voxarena/providers/` following the pattern in `gemini.py` / `openai.py`, wire it into `voxarena/harness.py` and `voxarena/config.py`, and open a PR.

For bugs and feature requests, please open an issue.

## License

[MIT](LICENSE).
