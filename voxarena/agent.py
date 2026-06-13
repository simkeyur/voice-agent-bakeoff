"""Agent definition — system prompt + tool schemas.

The bundled defaults ship the "Saffron Leaf" restaurant assistant under
``voxarena/data/saffron_leaf/`` so VoxArena runs end-to-end out of the box.

To evaluate your own agent, point ``data_dir`` at a directory containing a
``system_prompt.txt`` and edit ``voxarena/tools.py`` to register your tools.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from voxarena.tools import TOOL_SCHEMAS

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "saffron_leaf")


class Agent:
    """A versioned, hashable bundle of (system prompt + tool schemas).

    Args:
        prompt_version: Manifest tag for the prompt revision.
        tool_schema_version: Manifest tag for the tool schema revision.
        data_dir: Directory containing ``system_prompt.txt``. Defaults to the
            bundled Saffron Leaf example agent.
    """

    def __init__(
        self,
        prompt_version: str = "v1.0",
        tool_schema_version: str = "v1.0",
        data_dir: Optional[str] = None,
    ):
        self.prompt_version = prompt_version
        self.tool_schema_version = tool_schema_version
        self.data_dir = data_dir or DEFAULT_DATA_DIR

        self.prompt_path = os.path.join(self.data_dir, "system_prompt.txt")
        self.system_prompt = self._load_system_prompt()

        self.tool_schemas = TOOL_SCHEMAS

        self.prompt_hash = self._sha256(self.system_prompt)
        self.tool_schema_hash = self._sha256(json.dumps(self.tool_schemas, sort_keys=True))

    def _load_system_prompt(self) -> str:
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"System prompt file not found at {self.prompt_path}")
        with open(self.prompt_path, "r") as f:
            return f.read().strip()

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_agent_metadata(self) -> Dict[str, Any]:
        """Versioning and checksum info recorded in manifests."""
        return {
            "prompt_version": self.prompt_version,
            "prompt_hash": self.prompt_hash,
            "tool_schema_version": self.tool_schema_version,
            "tool_schema_hash": self.tool_schema_hash,
        }

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": s["name"],
                "description": s["description"],
                "parameters": s["parameters"],
            }
            for s in self.tool_schemas
        ]

    def get_gemini_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "function_declarations": [
                    {
                        "name": s["name"],
                        "description": s["description"],
                        "parameters": s["parameters"],
                    }
                ]
            }
            for s in self.tool_schemas
        ]
