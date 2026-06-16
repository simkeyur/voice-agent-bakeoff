"""Post-run LLM evaluator.

Runs after a session completes to semantically re-score turns whose
`expect.response_contains` block the rule-based checker already evaluated.

The LLM receives:
  - what the user said
  - what the agent replied
  - the list of expected intents from the utterance's `expect` block

No template-specific knowledge is embedded here — the intents come from the
template utterance definitions, so this works identically across all templates.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from voxarena.manifest import RunManifest, TurnMetric


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
                return json.loads(resp.text)

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
                return json.loads(resp.choices[0].message.content)

            return {"skipped": True, "reason": f"unsupported provider '{provider}'"}

        except Exception as e:
            logger.error(f"LLM evaluation call failed: {e}")
            return {"error": str(e)}

    def evaluate_response(
        self,
        text_input: str,
        transcript: str,
        expected_intents: List[str],
        partial: bool = False,
    ) -> Tuple[Optional[bool], str]:
        """Semantically judge whether the agent's reply satisfies the expected intents.

        Returns ``(passed, reasoning)``. Returns ``(None, reason)`` when the LLM
        is unavailable so callers can keep the rule-based result instead.
        When ``partial`` is True, the transcript was cut short by a barge-in —
        the LLM should judge whether the agent was on track to address the
        intents, not require completion.
        """
        system = (
            "You are an automated QA evaluator for a voice agent.\n"
            "Decide whether the agent's response satisfies ALL of the expected intent phrases.\n"
            "The phrases express semantic intent — judge meaning, not exact wording.\n"
            'Output JSON: {"passed": boolean, "reasoning": string}'
        )
        if partial:
            system += (
                "\nThe transcript was cut short before the agent finished. "
                "Pass if the partial response is clearly on track to satisfy the intents "
                "(e.g. acknowledging the request, calling the right tool, beginning the answer); "
                "fail only if it's off-topic or contradicts the intent."
            )
        user = (
            f'User said: "{text_input}"\n'
            f'Agent {"started replying" if partial else "replied"}: "{transcript}"\n'
            f"Expected intents: {json.dumps(expected_intents)}"
        )
        result = self._call_llm(system, user)
        if result.get("skipped") or result.get("error"):
            return None, result.get("reason") or result.get("error", "LLM unavailable")
        return bool(result.get("passed")), result.get("reasoning", "")

    def run_post_evaluation(
        self,
        manifest: RunManifest,
        utterances: List[Dict[str, Any]],
    ) -> int:
        """Re-score every turn that has a ``response_contains`` expect block.

        Updates ``turn.response_match``, ``turn.evaluation_passed``, and
        ``turn.evaluation_notes`` in-place. Returns the number of turns scored.
        """
        expect_map: Dict[str, Dict[str, Any]] = {
            u["id"]: u.get("expect") or {} for u in utterances
        }
        scored = 0

        for turn in manifest.turns:
            expect = expect_map.get(turn.utterance_id, {})
            intents = expect.get("response_contains")
            if not intents:
                continue
            # Only skip if there's literally no transcript to judge.
            transcript = turn.transcript_output or ""
            if not transcript.strip():
                continue

            partial = turn.interruption_sent_at is not None
            passed, reasoning = self.evaluate_response(
                turn.text_input, transcript, intents, partial=partial
            )
            if passed is None:
                # LLM unavailable — leave rule-based result intact.
                logger.debug(f"LLM eval skipped for turn {turn.utterance_id}: {reasoning}")
                continue

            turn.response_match = passed
            note = f"[LLM] {reasoning}"
            turn.evaluation_notes = (
                f"{turn.evaluation_notes} {note}".strip()
                if turn.evaluation_notes
                else note
            )
            scored += 1

        if scored:
            # Recompute evaluation_passed for each affected turn.
            for turn in manifest.turns:
                checks = [turn.tool_call_correct, turn.response_match]
                defined = [v for v in checks if v is not None]
                turn.evaluation_passed = all(defined) if defined else None

            logger.info(f"LLM post-evaluation: {scored}/{len(manifest.turns)} turn(s) re-scored.")

        return scored
