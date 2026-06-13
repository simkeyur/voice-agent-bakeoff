import os
import hashlib
import json
from typing import Dict, Any, List
from src.tools import TOOL_SCHEMAS

class SaffronLeafAgent:
    def __init__(self, prompt_version: str = "v1.0", tool_schema_version: str = "v1.0"):
        self.prompt_version = prompt_version
        self.tool_schema_version = tool_schema_version
        
        # Load system prompt
        self.prompt_path = os.path.join(
            os.path.dirname(__file__), "data", "system_prompt.txt"
        )
        self.system_prompt = self._load_system_prompt()
        
        # Load schemas
        self.tool_schemas = TOOL_SCHEMAS
        
        # Generate hashes for validation & manifests
        self.prompt_hash = self._calculate_sha256(self.system_prompt)
        self.tool_schema_hash = self._calculate_sha256(
            json.dumps(self.tool_schemas, sort_keys=True)
        )

    def _load_system_prompt(self) -> str:
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"System prompt file not found at {self.prompt_path}")
        with open(self.prompt_path, "r") as f:
            return f.read().strip()

    def _calculate_sha256(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_agent_metadata(self) -> Dict[str, Any]:
        """Return versioning and checksum info to record in manifests."""
        return {
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "tool_schema_version": self.tool_schema_version,
            "tool_schema_hash": self.tool_schema_hash
        }

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Format tools specifically for OpenAI Realtime API format."""
        openai_tools = []
        for schema in self.tool_schemas:
            openai_tools.append({
                "type": "function",
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"]
            })
        return openai_tools

    def get_gemini_tools(self) -> List[Dict[str, Any]]:
        """Format tools specifically for Gemini Live API format.
        Note: Pipecat's Gemini service often accepts tool schemas directly,
        or wrapped as function declarations. Let's provide a clean structure.
        """
        gemini_tools = []
        for schema in self.tool_schemas:
            gemini_tools.append({
                "function_declarations": [
                    {
                        "name": schema["name"],
                        "description": schema["description"],
                        "parameters": schema["parameters"]
                    }
                ]
            })
        return gemini_tools
