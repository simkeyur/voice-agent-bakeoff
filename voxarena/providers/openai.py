from typing import Any
from loguru import logger

from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime.events import SessionProperties, AudioConfiguration, AudioInput, AudioOutput
from pipecat.services.llm_service import FunctionCallParams
from src.providers.base import BaseProviderAdapter
from src.agent import SaffronLeafAgent
from src.config import ProviderConfig
from src.manifest import RunManifest
from src.tools import execute_tool

async def tool_callback(params: FunctionCallParams):
    """Symmetric function callback for handling tool calls from the LLM."""
    name = params.function_name
    args = params.arguments
    logger.info(f"[OpenAI Realtime] Tool call triggered: {name}({args})")
    
    try:
        result_str = execute_tool(name, args)
        # Wrap result in dict format if required
        result = {"result": result_str}
        logger.info(f"[OpenAI Realtime] Tool call resolved: {name} -> {result}")
        await params.result_callback(result)
    except Exception as e:
        logger.error(f"[OpenAI Realtime] Error in tool callback for {name}: {e}")
        await params.result_callback({"error": str(e)})

class OpenAIProviderAdapter(BaseProviderAdapter):
    """Adapter for OpenAI's Realtime API via Pipecat."""
    
    def __init__(self, agent: SaffronLeafAgent, config: ProviderConfig, manifest: RunManifest, api_key: str):
        super().__init__(agent, config, manifest)
        self.api_key = api_key

    def get_llm_service(self) -> OpenAIRealtimeLLMService:
        logger.info(f"Initializing OpenAI Realtime Service with model: {self.config.model}")
        
        # Format tools schema for OpenAI
        openai_tools = self.agent.get_openai_tools()
        
        # Build session properties
        session_properties = SessionProperties(
            instructions=self.agent.system_prompt,
            model=self.config.model,
            tools=openai_tools,
            output_modalities=["audio"],
            audio=AudioConfiguration(
                input=AudioInput(turn_detection=False),
                output=AudioOutput(voice="alloy")  # default voice (choices: alloy, echo, shimmer, etc.)
            )
        )
        
        # Instantiate OpenAIRealtimeLLMService
        service = OpenAIRealtimeLLMService(
            api_key=self.api_key,
            settings=OpenAIRealtimeLLMService.Settings(
                model=self.config.model,
                session_properties=session_properties
            )
        )
        
        # Register tool callbacks
        self.register_tools(service)
        return service

    def register_tools(self, service: OpenAIRealtimeLLMService) -> None:
        logger.info("Registering Saffron Leaf tools to OpenAI Realtime Service")
        for schema in self.agent.tool_schemas:
            tool_name = schema["name"]
            service.register_function(tool_name, tool_callback)
            logger.debug(f"Registered tool function: {tool_name}")
