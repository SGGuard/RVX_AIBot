"""
Custom exception classes for RVX Bot project.
Provides standardized error handling across the application.
"""


class RVXException(Exception):
    """Base exception for all RVX Bot errors."""
    
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.context = context or {}
        super().__init__(self.message)
    
    def to_user_message(self) -> str:
        """Return a user-friendly error message."""
        return f"❌ {self.message}"


# ============================================================================
# DATABASE ERRORS
# ============================================================================

class DatabaseError(RVXException):
    """Base exception for database-related errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка подключения к БД. Попробуй позже."


class QueryExecutionError(DatabaseError):
    """Raised when a database query fails."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка запроса к БД. Попробуй еще раз."


class DataIntegrityError(DatabaseError):
    """Raised when data integrity constraints are violated."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка целостности данных. Обратись в поддержку."


class TransactionError(DatabaseError):
    """Raised when a transaction fails."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка при сохранении данных. Попробуй еще раз."


# ============================================================================
# USER ERRORS
# ============================================================================

class UserError(RVXException):
    """Base exception for user-related errors."""
    pass


class UserNotFoundError(UserError):
    """Raised when a user is not found."""
    
    def to_user_message(self) -> str:
        return "❌ Пользователь не найден."


class UserAlreadyExistsError(UserError):
    """Raised when attempting to create a duplicate user."""
    
    def to_user_message(self) -> str:
        return "❌ Пользователь уже зарегистрирован."


class InsufficientXPError(UserError):
    """Raised when user has insufficient XP for an action."""
    
    def to_user_message(self) -> str:
        return "❌ Недостаточно XP для этого действия."


class UserBannedError(UserError):
    """Raised when user is banned."""
    
    def to_user_message(self) -> str:
        return "❌ Ты заблокирован. Обратись в поддержку."


# ============================================================================
# VALIDATION ERRORS
# ============================================================================

class ValidationError(RVXException):
    """Base exception for input validation errors."""
    pass


class InvalidInputError(ValidationError):
    """Raised when input validation fails."""
    
    def to_user_message(self) -> str:
        return f"❌ Неверный ввод: {self.message}"


class InvalidFormatError(ValidationError):
    """Raised when input format is invalid."""
    
    def to_user_message(self) -> str:
        return "❌ Неверный формат. Проверь ввод."


class RateLimitError(ValidationError):
    """Raised when rate limit is exceeded."""
    
    def to_user_message(self) -> str:
        return "❌ Ты отправляешь слишком много запросов. Подожди немного."


# ============================================================================
# AI / LLM ERRORS
# ============================================================================

class LLMError(RVXException):
    """Base exception for LLM-related errors."""
    pass


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка ИИ (timeout). Попробуй еще раз."


class LLMAPIError(LLMError):
    """Raised when LLM API returns an error."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка ИИ сервиса. Попробуй позже."


class LLMInvalidResponseError(LLMError):
    """Raised when LLM returns invalid response format."""
    
    def to_user_message(self) -> str:
        return "❌ ИИ вернул неверный ответ. Обратись в поддержку."


class LLMFallbackExhaustedError(LLMError):
    """Raised when all LLM providers fail."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка всех ИИ сервисов. Попробуй позже."


# ============================================================================
# BUSINESS LOGIC ERRORS
# ============================================================================

class BusinessLogicError(RVXException):
    """Base exception for business logic errors."""
    pass


class InvalidStateError(BusinessLogicError):
    """Raised when operation is invalid for current state."""
    
    def to_user_message(self) -> str:
        return "❌ Неверное состояние. Попробуй еще раз."


class DuplicateOperationError(BusinessLogicError):
    """Raised when operation was already completed."""
    
    def to_user_message(self) -> str:
        return "❌ Это действие уже выполнено."


class InsufficientFundsError(BusinessLogicError):
    """Raised when user has insufficient funds/resources."""
    
    def to_user_message(self) -> str:
        return "❌ Недостаточно ресурсов."


class OperationNotAllowedError(BusinessLogicError):
    """Raised when operation is not allowed."""
    
    def to_user_message(self) -> str:
        return "❌ Это действие не разрешено."


# ============================================================================
# EXTERNAL SERVICE ERRORS
# ============================================================================

class ExternalServiceError(RVXException):
    """Base exception for external service errors."""
    pass


class APIError(ExternalServiceError):
    """Raised when external API request fails."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка внешнего сервиса. Попробуй позже."


class NetworkError(ExternalServiceError):
    """Raised when network request fails."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка сети. Проверь интернет."


class TelegramAPIError(ExternalServiceError):
    """Raised when Telegram API returns an error."""
    
    def to_user_message(self) -> str:
        return "❌ Ошибка телеграм API. Попробуй позже."


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def handle_exception(exc: Exception, user_id: int = None, context: str = None) -> str:
    """
    Convert any exception to user-friendly message.
    
    Args:
        exc: The exception to handle
        user_id: ID of the user (for logging)
        context: Additional context (for logging)
    
    Returns:
        User-friendly error message
    """
    if isinstance(exc, RVXException):
        return exc.to_user_message()
    else:
        # Generic error for unknown exceptions
        return "❌ Неизвестная ошибка. Обратись в поддержку."
