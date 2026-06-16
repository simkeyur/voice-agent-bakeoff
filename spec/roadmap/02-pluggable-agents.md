# Phase 2 — Pluggable Agent Protocol

**Target version:** v0.3  
**Impact:** Expands the audience from "Gemini vs OpenAI users" to "anyone building a voice agent."

---

## Problem

VoxArena is currently hardwired to Gemini Live and OpenAI Realtime. A team building on:
- ElevenLabs Conversational AI
- Hume AI
- A custom WebRTC stack
- An internal model

…cannot use VoxArena at all today. This is the biggest limiter on adoption.

## Goal

```python
# User brings their own agent class
from voxarena import BaseVoiceAgent, run_eval

class MyAgent(BaseVoiceAgent):
    async def connect(self, system_prompt: str, tools: list[dict]) -> None:
        # initialize your agent session
        ...

    async def send_audio(self, audio_bytes: bytes) -> None:
        # send one utterance turn
        ...

    async def receive_response(self) -> AgentResponse:
        # return transcript + tool calls + audio + TTFA
        ...

    async def disconnect(self) -> None:
        ...

results = await run_eval(agent=MyAgent(), template="finance", turns=10)
```

---

## What to Build

### 1. `BaseVoiceAgent` abstract class

```python
# voxarena/agent_protocol.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class AgentResponse:
    transcript: str
    tool_calls: list[dict]          # [{name, args, result}]
    ttfa_ms: int | None             # time-to-first-audio in ms
    audio_bytes: bytes | None       # optional for recording

class BaseVoiceAgent(ABC):
    @abstractmethod
    async def connect(self, system_prompt: str, tools: list[dict]) -> None: ...

    @abstractmethod
    async def send_audio(self, audio_bytes: bytes) -> None: ...

    @abstractmethod
    async def receive_response(self) -> AgentResponse: ...

    @abstractmethod
    async def disconnect(self) -> None: ...
```

### 2. Provider registry

Built-in providers register themselves:

```python
# voxarena/providers/__init__.py
PROVIDERS = {
    "gemini": GeminiLiveAgent,
    "openai": OpenAIRealtimeAgent,
}
```

The CLI `--provider` flag resolves from this registry. Custom agents bypass it via `--agent-class`.

### 3. `run_eval()` programmatic API

```python
from voxarena import run_eval

results = await run_eval(
    agent=MyAgent(),
    template="finance",        # template ID or TemplateDef object
    turns=10,
    output="results.json",
)
```

This is the entry point for library use — no server, no UI, just a coroutine that returns structured results.

### 4. CLI `--agent-class` flag

```bash
voxarena run \
  --agent-class mypackage.agents.MyAgent \
  --template finance \
  --turns 10
```

VoxArena imports the class at runtime, instantiates it, and runs the eval loop.

---

## Implementation Notes

- Current `GeminiAgent` and `OpenAIAgent` should be refactored to implement `BaseVoiceAgent` — no logic changes, just conforming to the interface.
- The eval loop in `agent.py` should call only `BaseVoiceAgent` methods, making it provider-agnostic.
- `AgentResponse.tool_calls` should be normalized — each provider's raw format converted to `{name, args, result}` by the provider adapter, not the eval loop.
- Keep the existing WebRTC transport path working for the UI; the programmatic API uses direct-injection by default.

---

## Success Criteria

- A third-party agent (e.g. ElevenLabs or a mock) can be evaluated end-to-end using only `BaseVoiceAgent`.
- Existing Gemini and OpenAI runs continue to work unchanged.
- `examples/custom_agent.py` demonstrates a minimal working implementation.
