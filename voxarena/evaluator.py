import os
import json
import yaml
from typing import Dict, Any, List, Optional
from loguru import logger

from voxarena.config import get_setting, settings
from voxarena.manifest import RunManifest, TurnMetric

class SaffronLeafEvaluator:
    """Uses LLM models to automatically evaluate run transcripts and tool calls against ground truth."""
    
    def __init__(self, api_key: Optional[str] = None, provider: str = "gemini"):
        from voxarena.providers import api_key_env
        self.provider = provider
        if api_key is None:
            from voxarena.config import get_setting
            env_name = api_key_env(provider)
            api_key = get_setting(env_name)
        self.api_key = api_key
        
        # Load static knowledge base from the bundled Saffron Leaf demo data
        data_dir = os.path.join(os.path.dirname(__file__), "data", "saffron_leaf")
        with open(os.path.join(data_dir, "menu.json"), "r") as f:
            self.menu_data = f.read()
        with open(os.path.join(data_dir, "hours.json"), "r") as f:
            self.hours_data = f.read()

    def _call_llm_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Utility to invoke LLM and request structured JSON output."""
        eval_model = get_setting("EVALUATION_MODEL") or settings.EVALUATION_MODEL
        eval_provider = get_setting("EVALUATION_PROVIDER") or settings.EVALUATION_PROVIDER or ("openai" if "gpt" in eval_model.lower() else "gemini")

        from voxarena.providers import api_key_env
        env_name = api_key_env(eval_provider)
        api_key = get_setting(env_name)

        if not api_key:
            logger.warning(f"No API key available for Evaluator ({eval_provider}). Returning mock success evaluation.")
            return {"success": True, "mocked": True}
            
        try:
            if eval_provider == "gemini":
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=eval_model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        temperature=0.0
                    )
                )
                return json.loads(response.text)

            elif eval_provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=eval_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0
                )
                return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"LLM evaluation call failed: {e}")
            return {"error": str(e), "failed": True}

    def evaluate_tool_call(self, turn: TurnMetric, expect: Dict[str, Any]) -> Dict[str, Any]:
        """Reviewer 1: Verify if the tool called matches the expected outcomes."""
        system_prompt = """You are a software testing evaluator. Your job is to compare actual tool call execution against expected tool execution.
You must output a JSON object with:
- "correct": boolean (true if the tool name matches and arguments match or are semantically equivalent)
- "reasoning": string (explaining your decision)
"""
        user_prompt = f"""
Expected outcome: {json.dumps(expect)}
Actual tool execution: {json.dumps(turn.tool_call_details if turn.tool_call_details else None)}
User input text: "{turn.text_input}"
"""
        result = self._call_llm_json(system_prompt, user_prompt)
        return result

    def evaluate_hallucinations(self, turn: TurnMetric) -> Dict[str, Any]:
        """Reviewer 2: Check bot response against strict restaurant facts (menu & hours)."""
        system_prompt = f"""You are a facts compliance auditor for a restaurant called "The Bistro". 
Here is The Bistro's strict ground truth menu:
{self.menu_data}

Here are The Bistro's strict operating hours:
{self.hours_data}

Rules:
1. Bot must not invent dishes, prices, hours, or reservation slots not in the ground truth.
2. Bot must answer questions factually based on the menu and operating hours.

Compare the bot response text against the menu and hours. Identify if the bot hallucinated or made up any information.
Output a JSON object with:
- "hallucination_count": integer (0 if none)
- "hallucinations": array of objects containing "fact_mentioned" (string) and "error_explanation" (string)
"""
        user_prompt = f"""
User said: "{turn.text_input}"
Bot replied: "{turn.transcript_output}"
"""
        result = self._call_llm_json(system_prompt, user_prompt)
        return result

    def evaluate_run(self, manifest: RunManifest, utterances_file_path: str):
        """Run full evaluation suite over all turns in a manifest."""
        logger.info(f"Starting evaluation of run: {manifest.run_id}")
        
        # Load expected outcomes
        with open(utterances_file_path, "r") as f:
            utterances = yaml.safe_load(f)
            
        expect_map = {u["id"]: u.get("expect", {}) for u in utterances}
        
        total_hallucinations = 0
        correct_tool_calls = 0
        total_tool_calls_expected = 0
        
        for turn in manifest.turns:
            expect = expect_map.get(turn.utterance_id, {})
            
            # 1. Tool Call Evaluation
            if expect.get("tool") or (turn.tool_call_details and turn.tool_call_details.get("name")):
                total_tool_calls_expected += 1
                res = self.evaluate_tool_call(turn, expect)
                turn.tool_call_correct = res.get("correct", False)
                if turn.tool_call_correct:
                    correct_tool_calls += 1
                turn.evaluation_notes = res.get("reasoning", "")
                
            # 2. Hallucination Evaluation
            if turn.transcript_output:
                res_h = self.evaluate_hallucinations(turn)
                count = res_h.get("hallucination_count", 0)
                turn.hallucination_count = count
                total_hallucinations += count
                if count > 0:
                    turn.evaluation_notes = (turn.evaluation_notes or "") + f" | Hallucinations found: {res_h.get('hallucinations')}"

        # 3. Update Manifest metrics
        manifest.metrics.hallucination_count = total_hallucinations
        if total_tool_calls_expected > 0:
            manifest.metrics.tool_call_accuracy_rate = correct_tool_calls / total_tool_calls_expected
        else:
            manifest.metrics.tool_call_accuracy_rate = 1.0
            
        manifest.save()
        logger.success(f"Evaluation complete for {manifest.run_id}. Accuracy: {manifest.metrics.tool_call_accuracy_rate * 100:.1f}%, Hallucinations: {total_hallucinations}")
