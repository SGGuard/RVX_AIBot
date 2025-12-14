"""
API Client Service - управление вызовами к backend API.

DRY Principle: Единственное место для всех HTTP запросов к API.
"""

import httpx
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger("api_client")


class APIClientService:
    """API Client для общения с backend."""
    
    def __init__(self, api_url: str, api_key: str = "", timeout: float = 30.0, retry_attempts: int = 3):
        """
        Initialize API client.
        
        Args:
            api_url: Base API URL (e.g., http://localhost:8000)
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.request_counter = {"success": 0, "failure": 0, "fallback": 0}
        self.last_request_time: Optional[datetime] = None
    
    async def explain_news(self, text_content: str) -> Dict[str, Any]:
        """
        Send text to API for news analysis.
        
        Args:
            text_content: Text to analyze
            
        Returns:
            Dict with analysis results (summary_text, impact_points, simplified_text)
        """
        if not text_content or not text_content.strip():
            raise ValueError("Text content cannot be empty")
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        payload = {"text_content": text_content.strip()}
        
        for attempt in range(self.retry_attempts):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.api_url}/explain_news",
                        json=payload,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        self.request_counter["success"] += 1
                        self.last_request_time = datetime.now()
                        logger.info(f"✅ API request successful (attempt {attempt + 1})")
                        return response.json()
                    elif response.status_code == 429:  # Rate limit
                        logger.warning(f"⚠️ Rate limited, retrying... ({attempt + 1}/{self.retry_attempts})")
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    else:
                        logger.error(f"❌ API error {response.status_code}: {response.text}")
                        
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(f"⚠️ Network error (attempt {attempt + 1}): {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)
        
        self.request_counter["failure"] += 1
        raise ConnectionError(f"Failed to reach API after {self.retry_attempts} attempts")
    
    async def health_check(self) -> bool:
        """Check API health status."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get API client statistics."""
        return {
            "success": self.request_counter["success"],
            "failure": self.request_counter["failure"],
            "fallback": self.request_counter["fallback"],
            "total": sum(self.request_counter.values()),
            "last_request": self.last_request_time.isoformat() if self.last_request_time else None
        }
