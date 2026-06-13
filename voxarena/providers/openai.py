from loguru import logger

from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime.events import (
    SessionProperties,
    AudioConfiguration,
    AudioInput,
    AudioOutput,
)

from voxarena.providers.base import BaseProviderAdapter
from voxarena.agent import Agent
from voxarena.config import ProviderConfig
from voxarena.manifest import RunManifest


class OpenAIProviderAdapter(BaseProviderAdapter):
    """Adapter for OpenAI's Realtime API via Pipecat."""

    def __init__(self, agent: Agent, config: ProviderConfig, manifest: RunManifest, api_key: str):
        super().__init__(agent, config, manifest)
        self.api_key = api_key

    def get_llm_service(self) -> OpenAIRealtimeLLMService:
        logger.info(f"Initializing OpenAI Realtime Service with model: {self.config.model}")
        session_properties = SessionProperties(
            instructions=self.agent.system_prompt,
            model=self.config.model,
            tools=self.agent.get_openai_tools(),
            output_modalities=["audio"],
            audio=AudioConfiguration(
                input=AudioInput(turn_detection=False),
                output=AudioOutput(voice="alloy"),  # default voice (alloy, echo, shimmer, ...)
            ),
        )
        service = OpenAIRealtimeLLMService(
            api_key=self.api_key,
            settings=OpenAIRealtimeLLMService.Settings(
                model=self.config.model,
                session_properties=session_properties,
            ),
        )
        self.register_tools(service)
        return service
