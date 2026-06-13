from loguru import logger

from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams

from voxarena.providers.base import BaseProviderAdapter
from voxarena.agent import Agent
from voxarena.config import ProviderConfig
from voxarena.manifest import RunManifest


class GeminiProviderAdapter(BaseProviderAdapter):
    """Adapter for Google's Gemini Multimodal Live API via Pipecat."""

    def __init__(self, agent: Agent, config: ProviderConfig, manifest: RunManifest, api_key: str):
        super().__init__(agent, config, manifest)
        self.api_key = api_key

    def get_llm_service(self) -> GeminiLiveLLMService:
        logger.info(f"Initializing Gemini Live Service with model: {self.config.model}")
        service = GeminiLiveLLMService(
            api_key=self.api_key,
            system_instruction=self.agent.system_prompt,
            tools=self.agent.get_gemini_tools(),
            settings=GeminiLiveLLMService.Settings(
                model=self.config.model,
                voice="Puck",  # default premium voice (other choices: Charon, Aoede, Fenrir, Kore)
                vad=GeminiVADParams(disabled=True),
            ),
        )
        self.register_tools(service)
        return service
