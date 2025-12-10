"""
Type Hints Support v0.27.0
Gradual type annotation support with runtime validation.

Features:
- Type hint checking decorator
- Pydantic model validation
- Runtime type validation
- Backward compatibility with untyped functions
"""

import functools
import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar, Union, List, get_type_hints, get_origin, get_args
from pydantic import BaseModel, ValidationError, Field

logger = logging.getLogger(__name__)

T = TypeVar('T')


# =============================================================================
# TYPE VALIDATION DECORATORS
# =============================================================================

def validate_types(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to validate function argument types at runtime.
    ✅ CRITICAL FIX #6: Add type hints validation to critical functions
    
    Args:
        func: Function to decorate
        
    Returns:
        Decorated function with type checking
        
    Example:
        @validate_types
        def process_data(user_id: int, text: str) -> dict:
            return {"id": user_id, "text": text}
    """
    try:
        type_hints = get_type_hints(func)
    except Exception as e:
        logger.debug(f"⚠️ Could not extract type hints from {func.__name__}: {e}")
        return func
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Get function signature
        import inspect
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        
        # Validate each argument
        for param_name, param_value in bound_args.arguments.items():
            if param_name in type_hints:
                expected_type = type_hints[param_name]
                
                # Skip Optional type checking for None values
                if param_value is None:
                    if Union not in str(expected_type) and Optional not in str(expected_type):
                        logger.warning(
                            f"⚠️ {func.__name__}: {param_name} is None but type is {expected_type}"
                        )
                    continue
                
                # Check basic types
                if not _type_check(param_value, expected_type):
                    logger.warning(
                        f"⚠️ Type mismatch in {func.__name__}: "
                        f"{param_name}={param_value} expected {expected_type}"
                    )
        
        # Call function
        result = func(*args, **kwargs)
        
        # Validate return type
        if 'return' in type_hints:
            expected_return_type = type_hints['return']
            if not _type_check(result, expected_return_type):
                logger.warning(
                    f"⚠️ Return type mismatch in {func.__name__}: "
                    f"got {type(result)} expected {expected_return_type}"
                )
        
        return result
    
    return wrapper


def _type_check(value: Any, expected_type: Type) -> bool:
    """
    Check if value matches expected type.
    
    Args:
        value: Value to check
        expected_type: Expected type
        
    Returns:
        bool: True if type matches
    """
    # Handle None
    if value is None:
        return False
    
    # Handle Union/Optional
    if hasattr(expected_type, '__origin__'):
        origin = get_origin(expected_type)
        args = get_args(expected_type)
        
        if origin is Union:
            # For Union/Optional, check if value matches any of the types
            return any(_type_check(value, arg) if arg is not type(None) else value is None for arg in args)
        
        if origin is list:
            if not isinstance(value, list):
                return False
            if args and len(args) > 0:
                # Check first element type
                if value:
                    return _type_check(value[0], args[0])
            return True
        
        if origin is dict:
            return isinstance(value, dict)
    
    # Basic type check
    try:
        return isinstance(value, expected_type)
    except TypeError:
        # For complex types, just log
        return True


# =============================================================================
# PYDANTIC-BASED VALIDATION MODELS
# =============================================================================

class APIRequest(BaseModel):
    """Base model for API requests."""
    request_id: Optional[str] = Field(None, description="Request ID for tracing")
    timestamp: Optional[float] = Field(None, description="Request timestamp")


class APIResponse(BaseModel):
    """Base model for API responses."""
    success: bool = Field(True, description="Whether request succeeded")
    status_code: int = Field(200, description="HTTP status code")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[Dict] = Field(None, description="Response data")
    error: Optional[str] = Field(None, description="Error message if failed")


class AnalysisRequest(APIRequest):
    """Model for analysis requests."""
    text_content: str = Field(..., min_length=1, max_length=10000, description="Text to analyze")
    language: Optional[str] = Field("en", description="Content language")
    urgency: Optional[str] = Field("normal", description="Priority level")


class AnalysisResponse(APIResponse):
    """Model for analysis responses."""
    summary_text: Optional[str] = Field(None, description="Summary text")
    impact_points: Optional[List[str]] = Field(None, description="Impact points")
    simplified_text: Optional[str] = Field(None, description="Simplified explanation")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")


# =============================================================================
# TYPE VALIDATION HELPERS
# =============================================================================

def validate_request(request_data: Dict, model: Type[BaseModel]) -> tuple[bool, Union[BaseModel, str]]:
    """
    Validate request data against a Pydantic model.
    
    Args:
        request_data: Dictionary with request data
        model: Pydantic model class to validate against
        
    Returns:
        tuple: (is_valid, result_or_error_message)
    """
    try:
        validated = model(**request_data)
        return True, validated
    except ValidationError as e:
        error_msg = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
        logger.warning(f"⚠️ Validation error: {error_msg}")
        return False, error_msg


def get_type_hints_for_function(func: Callable) -> Dict[str, Type]:
    """
    Safely get type hints for a function.
    
    Args:
        func: Function to inspect
        
    Returns:
        Dict: Type hints mapping parameter names to types
    """
    try:
        return get_type_hints(func)
    except Exception as e:
        logger.debug(f"Could not get type hints for {func.__name__}: {e}")
        return {}


# =============================================================================
# CRITICAL FUNCTIONS WITH TYPE HINTS
# =============================================================================

@validate_types
def sanitize_text_for_analysis(text: str, max_length: int = 10000) -> str:
    """
    Sanitize text for AI analysis with type hints validation.
    
    Args:
        text: Input text
        max_length: Maximum text length
        
    Returns:
        str: Sanitized text
    """
    if not isinstance(text, str):
        logger.warning(f"Expected str, got {type(text)}")
        text = str(text)
    
    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')
    
    # Truncate if needed
    if len(text) > max_length:
        text = text[:max_length]
    
    return text.strip()


@validate_types
def parse_analysis_response(response_text: str) -> Optional[Dict]:
    """
    Parse AI analysis response with type hints validation.
    
    Args:
        response_text: Response from AI
        
    Returns:
        Dict: Parsed response or None if parsing failed
    """
    if not isinstance(response_text, str):
        logger.error(f"Expected str response, got {type(response_text)}")
        return None
    
    import json
    
    # Extract JSON from response
    try:
        if '<json>' in response_text and '</json>' in response_text:
            json_str = response_text.split('<json>')[1].split('</json>')[0]
        else:
            json_str = response_text
        
        data = json.loads(json_str)
        return data
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"Failed to parse response: {e}")
        return None


@validate_types
def validate_analysis_output(data: Dict) -> tuple[bool, Optional[str]]:
    """
    Validate AI analysis output has required fields with type hints.
    
    Args:
        data: Analysis output dictionary
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, f"Expected dict, got {type(data)}"
    
    required_fields = ['summary_text', 'impact_points']
    
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
        
        if field == 'summary_text' and not isinstance(data[field], str):
            return False, f"{field} must be str, got {type(data[field])}"
        
        if field == 'impact_points' and not isinstance(data[field], list):
            return False, f"{field} must be list, got {type(data[field])}"
    
    return True, None
