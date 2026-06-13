from typing import Any
from loguru import logger

from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiVADParams
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
    logger.info(f"[Gemini Live] Tool call triggered: {name}({args})")
    
    try:
        result_str = execute_tool(name, args)
        # Wrap result in dict format if required, otherwise string
        result = {"result": result_str}
        logger.info(f"[Gemini Live] Tool call resolved: {name} -> {result}")
        await params.result_callback(result)
    except Exception as e:
        logger.error(f"[Gemini Live] Error in tool callback for {name}: {e}")
        await params.result_callback({"error": str(e)})

class GeminiProviderAdapter(BaseProviderAdapter):
    """Adapter for Google's Gemini Multimodal Live API via Pipecat."""
    
    def __init__(self, agent: SaffronLeafAgent, config: ProviderConfig, manifest: RunManifest, api_key: str):
        super().__init__(agent, config, manifest)
        self.api_key = api_key

    def get_llm_service(self) -> GeminiLiveLLMService:
        logger.info(f"Initializing Gemini Live Service with model: {self.config.model}")
        
        # Format tools schema for Gemini
        gemini_tools = self.agent.get_gemini_tools()
        
        # Instantiate GeminiLiveLLMService
        service = GeminiLiveLLMService(
            api_key=self.api_key,
            system_instruction=self.agent.system_prompt,
            tools=gemini_tools,
            settings=GeminiLiveLLMService.Settings(
                model=self.config.model,
                voice="Puck",  # default premium voice (other choices: Charon, Aoede, Fenrir, Kore)
                vad=GeminiVADParams(disabled=True)
            )
        )

        
        # Register tool callbacks
        self.register_tools(service)
        return service

    def register_tools(self, service: GeminiLiveLLMService) -> None:
        logger.info("Registering Saffron Leaf tools to Gemini Live Service")
        for schema in self.agent.tool_schemas:
            tool_name = schema["name"]
            service.register_function(tool_name, tool_callback)
            logger.debug(f"Registered tool function: {tool_name}")
