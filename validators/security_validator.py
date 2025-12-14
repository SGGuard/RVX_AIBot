"""
Security Validation Module (DRY - Centralized security checks)
============================================================

All security validation rules in one place to prevent duplication.
"""

from dataclasses import dataclass
from typing import List
import re


@dataclass
class SecurityValidationResult:
    """Result of security validation"""
    is_safe: bool
    threats: List[str]
    
    def __bool__(self) -> bool:
        return self.is_safe
    
    def threat_message(self) -> str:
        """Returns formatted threat message"""
        if not self.threats:
            return ""
        return "🚨 " + "\n🚨 ".join(self.threats)


class SecurityValidator:
    """
    Centralized security validator (DRY principle)
    
    All dangerous patterns are defined here.
    
    Usage:
        from validators import SecurityValidator
        
        result = SecurityValidator.validate(user_input)
        if not result:
            logger.warning(f"Security threat: {result.threat_message()}")
    """
    
    # Single source of truth for security patterns
    DANGEROUS_PATTERNS = [
        # SQL Injection
        (r"DROP\s+TABLE", "SQL Injection attempt (DROP TABLE)"),
        (r"DELETE\s+FROM", "SQL Injection attempt (DELETE FROM)"),
        (r"INSERT\s+INTO", "SQL Injection attempt (INSERT INTO)"),
        (r"UPDATE\s+.*SET", "SQL Injection attempt (UPDATE SET)"),
        (r"UNION\s+SELECT", "SQL Injection attempt (UNION SELECT)"),
        (r"SELECT\s+.*FROM", "SQL Injection attempt (SELECT FROM)"),
        
        # XSS
        (r"<script[^>]*>", "XSS Injection attempt (script tag)"),
        (r"javascript:", "XSS Injection attempt (javascript protocol)"),
        (r"on\w+\s*=", "XSS Injection attempt (event handler)"),
        (r"<iframe", "XSS Injection attempt (iframe tag)"),
        (r"<embed", "XSS Injection attempt (embed tag)"),
        
        # Command Injection
        (r";\s*exec\s*\(", "Command Injection attempt (exec)"),
        (r";\s*eval\s*\(", "Command Injection attempt (eval)"),
        (r"\|\s*sh", "Command Injection attempt (shell pipe)"),
        (r"`.*`", "Command Injection attempt (backticks)"),
        
        # Path Traversal
        (r"\.\./", "Path Traversal attempt"),
        (r"\.\.\%2f", "Path Traversal attempt (encoded)"),
        
        # LDAP Injection
        (r"\*\(\|", "LDAP Injection attempt"),
    ]
    
    MAX_MESSAGE_LENGTH = 5000  # Prevent very large messages
    
    @classmethod
    def validate(cls, text: str) -> SecurityValidationResult:
        """
        Validates text for security threats
        
        Args:
            text: Text to validate
            
        Returns:
            SecurityValidationResult with is_safe flag and threat list
        """
        threats = []
        
        # Check size
        if len(text) > cls.MAX_MESSAGE_LENGTH:
            threats.append(f"Message too large (max {cls.MAX_MESSAGE_LENGTH} chars)")
            return SecurityValidationResult(is_safe=False, threats=threats)
        
        # Check for dangerous patterns
        for pattern, description in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                threats.append(description)
        
        return SecurityValidationResult(
            is_safe=len(threats) == 0,
            threats=threats
        )
    
    @classmethod
    def validate_or_raise(cls, text: str) -> str:
        """
        Validates text or raises exception
        
        Args:
            text: Text to validate
            
        Raises:
            Exception: If security threats found
            
        Returns:
            Original text if safe
        """
        result = cls.validate(text)
        if not result.is_safe:
            raise Exception(f"Security violation: {result.threat_message()}")
        return text
    
    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Sanitizes potentially dangerous characters
        
        Args:
            text: Text to sanitize
            
        Returns:
            Sanitized text
        """
        # Remove control characters
        text = "".join(char for char in text if ord(char) >= 32 or char in "\n\r\t")
        
        # Remove multiple spaces
        text = re.sub(r" +", " ", text)
        
        # Remove multiple newlines
        text = re.sub(r"\n\n+", "\n", text)
        
        return text.strip()
