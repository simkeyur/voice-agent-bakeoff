"""Post-run LLM evaluator.

Runs after a session completes to semantically score each turn:

- **Response match** — does the agent's reply satisfy the per-utterance
  ``expect.response_contains`` intents (semantic, not keyword)?
- **Faithfulness** — when a tool was called, does the reply stay true to
  the tool's actual result string (no invented numbers/names)?
- **Conciseness** — is the reply appropriately brief for a voice channel?
- **Hallucinations** — count of factual claims in the reply that aren't
  supported by the tool result or by the user's input.

All checks are template-agnostic — they read only the per-turn fields the
harness already records, so the same code works across every template.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from voxarena.manifest import RunManifest, TurnMetric


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON parse: handles raw JSON, fenced blocks, or JSON embedded in prose."""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fenced ```json ... ``` blocks
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # First top-level object substring
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


class LLMEvaluator:
    """Semantic scorer backed by the configured EVALUATION_MODEL."""

    def _call_llm(self, system: str, user: str) -> Dict[str, Any]:
        from voxarena.config import get_setting, settings
        from voxarena.providers import api_key_env

        model = get_setting("EVALUATION_MODEL") or settings.EVALUATION_MODEL
        provider = get_setting("EVALUATION_PROVIDER") or settings.EVALUATION_PROVIDER
        api_key = get_setting(api_key_env(provider))

        if not api_key:
            return {"skipped": True, "reason": f"no API key for {provider}"}

        try:
            if provider == "gemini":
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                resp = client.models.generate_content(
                    model=model,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                parsed = _extract_json(resp.text or "")
                if parsed is None:
                    logger.warning(f"LLM eval (gemini) returned unparseable JSON: {resp.text!r}")
                    return {"error": "unparseable JSON response"}
                return parsed

            if provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                )
                raw = resp.choices[0].message.content or ""
                parsed = _extract_json(raw)
                if parsed is None:
                    logger.warning(f"LLM eval (openai) returned unparseable JSON: {raw!r}")
                    return {"error": "unparseable JSON response"}
                return parsed

            return {"skipped": True, "reason": f"unsupported provider '{provider}'"}

        except Exception as e:
            logger.error(f"LLM evaluation call failed ({provider}/{model}): {e}")
            return {"error": str(e)}

    def _judge_bool(
        self, system: str, user: str, fallback_reason: str = "LLM unavailable"
    ) -> Tuple[Optional[bool], str]:
        """Common harness for boolean checks. Returns (passed, reasoning)."""
        result = self._call_llm(system, user)
        if result.get("skipped") or result.get("error"):
            return None, result.get("reason") or result.get("error", fallback_reason)
        return bool(result.get("passed")), str(result.get("reasoning") or "")

    def evaluate_response(
        self,
        text_input: str,
        transcript: str,
        expected_intents: List[str],
        partial: bool = False,
    ) -> Tuple[Optional[bool], str]:
        """Did the reply satisfy the per-utterance intent phrases?"""
        completion_clause = (
            "The transcript was cut short by a barge-in before the agent could finish. "
            "Pass if the partial reply is clearly addressing the right intents "
            "(acknowledged the request, called the right tool, started the right answer). "
            "Fail only if the partial reply is off-topic or contradicts the intents."
            if partial
            else "Pass if the reply clearly addresses the intents in meaning, even if it uses "
            "different words. Fail if it ignores them, contradicts them, or goes off-topic."
        )
        system = (
            "You are an automated QA judge for a voice agent.\n"
            "Decide whether the agent's reply satisfies the expected intent phrases.\n"
            "Judge semantic meaning, not exact wording.\n"
            f"{completion_clause}\n"
            'Respond with ONLY a JSON object: {"passed": true|false, "reasoning": "<one sentence>"}'
        )
        user = (
            f'User input: "{text_input}"\n'
            f'Agent reply: "{transcript}"\n'
            f"Expected intents: {json.dumps(expected_intents)}"
        )
        return self._judge_bool(system, user)

    def evaluate_faithfulness(
        self, text_input: str, transcript: str, tool_result: str
    ) -> Tuple[Optional[bool], str]:
        """When a tool was called, did the reply faithfully reflect its result?"""
        system = (
            "You are a faithfulness auditor for a voice agent.\n"
            "The agent received a tool result and then spoke a reply to the user.\n"
            "Pass if every concrete fact in the reply (numbers, names, prices, dates, "
            "statuses, IDs) is supported by the tool result. Paraphrasing and "
            "summarization are fine; contradicting or inventing facts is not.\n"
            'Respond with ONLY a JSON object: {"passed": true|false, "reasoning": "<one sentence>"}'
        )
        user = (
            f'User input: "{text_input}"\n'
            f'Tool result: "{tool_result}"\n'
            f'Agent reply: "{transcript}"'
        )
        return self._judge_bool(system, user)

    def evaluate_conciseness(
        self, text_input: str, transcript: str
    ) -> Tuple[Optional[bool], str]:
        """Is the reply appropriately brief for a voice channel?"""
        system = (
            "You are evaluating a voice agent's reply for brevity.\n"
            "Voice replies should sound conversational and concise — long monologues are bad UX.\n"
            "Pass if the reply is one to three short sentences for a simple confirmation, or "
            "a bit longer only when conveying genuinely complex information.\n"
            "Fail if the reply is verbose, repetitive, padded with filler, or reads like "
            "written prose rather than natural speech.\n"
            'Respond with ONLY a JSON object: {"passed": true|false, "reasoning": "<one sentence>"}'
        )
        user = (
            f'User input: "{text_input}"\n'
            f'Agent reply: "{transcript}"'
        )
        return self._judge_bool(system, user)

    def evaluate_hallucinations(
        self,
        text_input: str,
        transcript: str,
        tool_result: Optional[str],
    ) -> Tuple[Optional[int], str]:
        """Count factual inventions in the reply.

        Grounding sources for the reply:
        - the user's own input,
        - the tool result (if any),
        - general world knowledge for non-domain claims (greetings, well-known facts).

        Anything stated as concrete fact (a number, name, status, claim about the
        business) that isn't supported by those grounds counts as a hallucination.
        """
        grounding = (
            f"Tool result available: \"{tool_result}\""
            if tool_result
            else "No tool was called — the agent has no domain ground truth, so any "
            "specific domain facts in the reply are hallucinations."
        )
        system = (
            "You are a hallucination detector for a voice agent.\n"
            "Count the number of factual claims in the agent's reply that are NOT supported "
            "by the user's input, the tool result, or obvious general knowledge.\n"
            "Examples that count: invented prices, made-up business hours, fabricated names, "
            "stated statuses that contradict the tool result, claims about policies that "
            "weren't in the tool result.\n"
            "Examples that DO NOT count: greetings, paraphrases of the tool result, asking "
            "clarifying questions, general politeness.\n"
            'Respond with ONLY a JSON object: '
            '{"count": <integer 0+>, "items": ["<short fact 1>", ...], "reasoning": "<one sentence>"}'
        )
        user = (
            f'User input: "{text_input}"\n'
            f'{grounding}\n'
            f'Agent reply: "{transcript}"'
        )
        result = self._call_llm(system, user)
        if result.get("skipped") or result.get("error"):
            return None, result.get("reason") or result.get("error", "LLM unavailable")
        try:
            count = int(result.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        items = result.get("items") or []
        reasoning = str(result.get("reasoning") or "")
        if items:
            reasoning = f"{reasoning} ({', '.join(str(i) for i in items)})".strip()
        return max(count, 0), reasoning

    def run_post_evaluation(
        self,
        manifest: RunManifest,
        utterances: List[Dict[str, Any]],
    ) -> int:
        """Score every turn with the available LLM checks. Returns the number of
        turns touched. Updates per-turn fields and aggregate rates in place."""
        expect_map: Dict[str, Dict[str, Any]] = {
            u["id"]: u.get("expect") or {} for u in utterances
        }
        scored = 0

        for turn in manifest.turns:
            transcript = (turn.transcript_output or "").strip()
            if not transcript:
                continue

            expect = expect_map.get(turn.utterance_id, {})
            intents = expect.get("response_contains")
            partial = turn.interruption_sent_at is not None
            tool_result = None
            if turn.tool_call_details:
                tool_result = (
                    turn.tool_call_details.get("result")
                    or turn.tool_call_details.get("result_str")
                )
                if tool_result is not None:
                    tool_result = str(tool_result)

            touched = False
            notes: List[str] = []

            # Response match
            if intents:
                passed, reasoning = self.evaluate_response(
                    turn.text_input, transcript, intents, partial=partial
                )
                if passed is not None:
                    turn.response_match = passed
                    notes.append(f"Response: {reasoning}")
                    touched = True

            # Faithfulness — only when we have a tool result to compare against.
            if tool_result:
                passed, reasoning = self.evaluate_faithfulness(
                    turn.text_input, transcript, tool_result
                )
                if passed is not None:
                    turn.faithfulness_passed = passed
                    notes.append(f"Faithfulness: {reasoning}")
                    touched = True

            # Conciseness — skip partial turns (the agent didn't get to finish).
            if not partial:
                passed, reasoning = self.evaluate_conciseness(turn.text_input, transcript)
                if passed is not None:
                    turn.conciseness_passed = passed
                    notes.append(f"Conciseness: {reasoning}")
                    touched = True

            # Hallucinations — counts factual inventions, overrides any prior rule-based count.
            count, reasoning = self.evaluate_hallucinations(
                turn.text_input, transcript, tool_result
            )
            if count is not None:
                turn.hallucination_count = count
                notes.append(f"Hallucinations: {count} — {reasoning}")
                touched = True

            if touched:
                scored += 1
                combined = "[Eval] " + " | ".join(notes)
                turn.evaluation_notes = (
                    f"{turn.evaluation_notes} {combined}".strip()
                    if turn.evaluation_notes
                    else combined
                )

        if scored:
            for turn in manifest.turns:
                checks = [
                    turn.tool_call_correct,
                    turn.response_match,
                    turn.faithfulness_passed,
                    turn.conciseness_passed,
                ]
                defined = [v for v in checks if v is not None]
                hall_ok = (turn.hallucination_count or 0) == 0
                turn.evaluation_passed = all(defined) and hall_ok if defined else (hall_ok if turn.hallucination_count is not None else None)

            self._recompute_aggregates(manifest)
            logger.info(f"LLM post-evaluation: {scored}/{len(manifest.turns)} turn(s) scored.")

        return scored

    @staticmethod
    def _recompute_aggregates(manifest: RunManifest) -> None:
        """Refresh aggregate rates after LLM eval updates per-turn fields."""
        turns = manifest.turns
        m = manifest.metrics

        def rate(attr: str) -> Optional[float]:
            scored = [getattr(t, attr) for t in turns if getattr(t, attr) is not None]
            if not scored:
                return None
            return sum(1 for v in scored if v) / len(scored)

        m.response_match_rate = rate("response_match")
        m.faithfulness_rate = rate("faithfulness_passed")
        m.conciseness_rate = rate("conciseness_passed")
        m.hallucination_count = sum(t.hallucination_count or 0 for t in turns)
