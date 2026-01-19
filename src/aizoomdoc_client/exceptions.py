"""
Исключения для AIZoomDoc Client.
"""

from typing import Optional, Dict, Any


class AIZoomDocError(Exception):
    """Базовое исключение для AIZoomDoc Client."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class AuthenticationError(AIZoomDocError):
    """Ошибка аутентификации."""
    pass


class TokenExpiredError(AuthenticationError):
    """Токен истёк и refresh не удался."""
    pass


class APIError(AIZoomDocError):
    """Ошибка API запроса."""
    
    def __init__(
        self,
        message: str,
        status_code: int,
        error_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.error_type = error_type
        super().__init__(message, details)


class NotFoundError(APIError):
    """Ресурс не найден (404)."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=404, error_type="not_found", details=details)


class ServerError(APIError):
    """Внутренняя ошибка сервера (5xx)."""
    
    def __init__(self, message: str = "Server error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=500, error_type="server_error", details=details)


class ValidationError(APIError):
    """Ошибка валидации данных (400/422)."""
    
    def __init__(self, message: str = "Validation error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status_code=422, error_type="validation_error", details=details)


