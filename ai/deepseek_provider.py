"""
DeepSeek AI Provider Implementation
===================================
"""

import logging
import time
from typing import Dict, Any
from openai import OpenAI
from .interface import AIProvider, AIResponse, HealthStatus, AIException

logger = logging.getLogger("DEEPSEEK_PROVIDER")


class DeepSeekProvider(AIProvider):
    """DeepSeek AI provider implementation"""
    
    def __init__(self, api_key: str, model: str = "deepseek-chat", 
                 temperature: float = 0.3, max_tokens: int = 1500):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
    
    @property
    def client(self) -> OpenAI:
        """Lazy initialization of OpenAI client"""
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client
    
    async def analyze(self, text: str) -> AIResponse:
        """Analyze text using DeepSeek"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": text}],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            result_text = response.choices[0].message.content
            parsed = self._parse_response(result_text)
            
            return AIResponse(
                summary_text=parsed.get("summary_text", result_text),
                impact_points=parsed.get("impact_points", []),
                confidence=parsed.get("confidence", 0.8),
                provider="deepseek",
                raw_response={"text": result_text}
            )
        except Exception as e:
            logger.error(f"DeepSeek analyze error: {e}")
            raise AIException(f"DeepSeek error: {str(e)}")
    
    async def health_check(self) -> HealthStatus:
        """Check DeepSeek availability"""
        start = time.time()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=10,
                temperature=0.3
            )
            latency = (time.time() - start) * 1000
            return HealthStatus(is_healthy=True, latency_ms=latency)
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"DeepSeek health check failed: {e}")
            return HealthStatus(
                is_healthy=False,
                latency_ms=latency,
                error=str(e)
            )
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse DeepSeek response (supports JSON format)"""
        import json
        import re
        
        # Try to extract JSON from response
        match = re.search(r'<json>(.*?)</json>', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Fallback: return raw text
        return {
            "summary_text": text,
            "impact_points": [],
            "confidence": 0.7
        }
