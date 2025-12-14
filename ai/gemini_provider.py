"""
Gemini AI Provider Implementation
================================
"""

import logging
import time
from typing import Dict, Any
from google import genai
from .interface import AIProvider, AIResponse, HealthStatus, AIException

logger = logging.getLogger("GEMINI_PROVIDER")


class GeminiProvider(AIProvider):
    """Google Gemini AI provider implementation"""
    
    def __init__(self, api_key: str, model: str = "models/gemini-2.5-flash",
                 temperature: float = 0.3, max_tokens: int = 1500):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
    
    @property
    def client(self) -> genai.Client:
        """Lazy initialization of Gemini client"""
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client
    
    async def analyze(self, text: str) -> AIResponse:
        """Analyze text using Gemini"""
        try:
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(text)
            
            result_text = response.text
            parsed = self._parse_response(result_text)
            
            return AIResponse(
                summary_text=parsed.get("summary_text", result_text),
                impact_points=parsed.get("impact_points", []),
                confidence=parsed.get("confidence", 0.8),
                provider="gemini",
                raw_response={"text": result_text}
            )
        except Exception as e:
            logger.error(f"Gemini analyze error: {e}")
            raise AIException(f"Gemini error: {str(e)}")
    
    async def health_check(self) -> HealthStatus:
        """Check Gemini availability"""
        start = time.time()
        try:
            model = genai.GenerativeModel(self.model)
            model.generate_content("test")
            latency = (time.time() - start) * 1000
            return HealthStatus(is_healthy=True, latency_ms=latency)
        except Exception as e:
            latency = (time.time() - start) * 1000
            logger.error(f"Gemini health check failed: {e}")
            return HealthStatus(
                is_healthy=False,
                latency_ms=latency,
                error=str(e)
            )
    
    def _parse_response(self, text: str) -> Dict[str, Any]:
        """Parse Gemini response (supports JSON format)"""
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
