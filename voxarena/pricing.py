"""Approximate per-token pricing for realtime models.

`LLMTokenUsage` (from Pipecat's usage-metrics frames) reports a single
prompt/completion token count without breaking out audio vs. text tokens, so
these rates are a flat blended approximation — good enough for relative
provider comparison, not for exact billing reconciliation.

Update this table as vendor pricing changes or new models are added to
`voxarena/config.py`.
"""

from typing import Dict, Optional, TypedDict


class ModelRate(TypedDict):
    input_per_million: float
    output_per_million: float


MODEL_PRICING: Dict[str, ModelRate] = {
    "gemini-3.1-flash-live-preview": {"input_per_million": 0.50, "output_per_million": 2.00},
    "gpt-realtime-2": {"input_per_million": 4.00, "output_per_million": 16.00},
}


def estimate_cost(model: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[float]:
    """Return an estimated USD cost for a turn's token usage, or None if the
    model has no pricing entry or token counts are unavailable."""
    rate = MODEL_PRICING.get(model)
    if rate is None or prompt_tokens is None or completion_tokens is None:
        return None

    return (
        prompt_tokens * rate["input_per_million"] / 1_000_000
        + completion_tokens * rate["output_per_million"] / 1_000_000
    )
