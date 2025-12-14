"""
AI Providers Interface (SOLID - OCP + LSP + DIP)
================================================

Abstract interface for all AI providers.
Allows adding new providers without modifying existing code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class AIException(Exception):
    """Base exception for AI provider errors"""
    pass


@dataclass
class AIResponse:
    """Unified response format for all AI providers"""
    summary_text: str
    impact_points: list
    confidence: float
    provider: str
    raw_response: Dict[str, Any]


@dataclass
class HealthStatus:
    """Health check status"""
    is_healthy: bool
    latency_ms: float
    error: Optional[str] = None


class AIProvider(ABC):
    """
    Abstract base class for all AI providers (SOLID principle)
    
    Any new provider must implement these methods.
    Ensures all providers have the same interface.
    """
    
    @abstractmethod
    async def analyze(self, text: str) -> AIResponse:
        """
        Analyze text and return structured response
        
        Args:
            text: Text to analyze
            
        Returns:
            AIResponse with structured analysis
            
        Raises:
            AIException: If analysis fails
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Check provider availability
        
        Returns:
            HealthStatus with is_healthy flag and latency
        """
        pass
    
    def get_name(self) -> str:
        """Get provider name"""
        return self.__class__.__name__
