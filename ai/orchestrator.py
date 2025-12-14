"""
AI Provider Factory & Orchestrator (OCP + DIP)
==============================================

Factory for creating providers and orchestrator for managing them.
"""

import logging
from typing import Optional, Dict
from .interface import AIProvider, AIResponse, HealthStatus, AIException
from .deepseek_provider import DeepSeekProvider
from .gemini_provider import GeminiProvider

logger = logging.getLogger("AI_ORCHESTRATOR")


class AIProviderFactory:
    """Factory for creating AI providers (Design Pattern: Factory Method)"""
    
    _providers: Dict[str, type] = {
        "deepseek": DeepSeekProvider,
        "gemini": GeminiProvider,
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type):
        """
        Register new provider (OCP - Open for extension)
        
        Args:
            name: Provider name
            provider_class: Provider class that implements AIProvider
        """
        cls._providers[name] = provider_class
        logger.info(f"Registered AI provider: {name}")
    
    @classmethod
    def create(cls, provider_name: str, **kwargs) -> AIProvider:
        """
        Create provider instance
        
        Args:
            provider_name: Name of provider (deepseek, gemini, etc.)
            **kwargs: Provider-specific arguments
            
        Returns:
            AIProvider instance
            
        Raises:
            ValueError: If provider not found
        """
        if provider_name not in cls._providers:
            raise ValueError(
                f"Unknown provider: {provider_name}. "
                f"Available: {', '.join(cls._providers.keys())}"
            )
        
        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)
    
    @classmethod
    def get_available(cls) -> list:
        """Get list of available providers"""
        return list(cls._providers.keys())


class AIOrchestrator:
    """
    Orchestrates multiple AI providers with fallback strategy
    
    Usage:
        orchestrator = AIOrchestrator(
            primary=primary_provider,
            fallback=fallback_provider
        )
        response = await orchestrator.analyze(text)
    """
    
    def __init__(self, primary: AIProvider, fallback: Optional[AIProvider] = None):
        self.primary = primary
        self.fallback = fallback
        self.last_provider_used = None
    
    async def analyze(self, text: str) -> AIResponse:
        """
        Analyze text with fallback strategy
        
        First tries primary provider, then fallback if available.
        
        Args:
            text: Text to analyze
            
        Returns:
            AIResponse from available provider
            
        Raises:
            AIException: If all providers fail
        """
        # Try primary provider
        try:
            logger.debug(f"Using primary provider: {self.primary.get_name()}")
            response = await self.primary.analyze(text)
            self.last_provider_used = self.primary.get_name()
            return response
        except AIException as e:
            logger.warning(f"Primary provider failed: {e}")
            
            if self.fallback is None:
                raise
        
        # Try fallback provider
        if self.fallback:
            try:
                logger.debug(f"Falling back to: {self.fallback.get_name()}")
                response = await self.fallback.analyze(text)
                self.last_provider_used = self.fallback.get_name()
                logger.info(f"Successfully used fallback provider: {self.fallback.get_name()}")
                return response
            except AIException as e:
                logger.error(f"Fallback provider also failed: {e}")
                raise AIException(
                    f"All AI providers failed. Primary: {self.primary.get_name()}, "
                    f"Fallback: {self.fallback.get_name() if self.fallback else 'None'}"
                )
        
        raise AIException("No AI providers available")
    
    async def health_check(self) -> Dict[str, HealthStatus]:
        """
        Check health of all providers
        
        Returns:
            Dict with provider names as keys and HealthStatus as values
        """
        status = {}
        
        # Check primary
        try:
            status["primary"] = await self.primary.health_check()
        except Exception as e:
            status["primary"] = HealthStatus(
                is_healthy=False,
                latency_ms=0,
                error=str(e)
            )
        
        # Check fallback if available
        if self.fallback:
            try:
                status["fallback"] = await self.fallback.health_check()
            except Exception as e:
                status["fallback"] = HealthStatus(
                    is_healthy=False,
                    latency_ms=0,
                    error=str(e)
                )
        
        return status
    
    def get_healthy_provider(self) -> Optional[str]:
        """Get name of currently healthy provider"""
        return self.last_provider_used
