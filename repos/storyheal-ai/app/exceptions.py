"""Custom exception classes for the application."""

import uuid
from typing import Any, Dict, Optional


class StoryHealAIServiceException(Exception):
    """Base exception for StoryHeal AI Service."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(StoryHealAIServiceException):
    """Authentication failed."""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, "AUTHENTICATION_FAILED", details)


class AuthorizationError(StoryHealAIServiceException):
    """Authorization failed."""

    def __init__(
        self,
        message: str = "Access denied",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, "ACCESS_DENIED", details)


class NotFoundError(StoryHealAIServiceException):
    """Resource not found."""

    def __init__(
        self,
        resource: str,
        resource_id: Optional[uuid.UUID] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        message = f"{resource} not found"
        if resource_id:
            message += f" (ID: {resource_id})"
        
        error_details = details or {}
        if resource_id:
            error_details["resource_id"] = str(resource_id)
        error_details["resource_type"] = resource
        
        super().__init__(message, f"{resource.upper()}_NOT_FOUND", error_details)


class ValidationError(StoryHealAIServiceException):
    """Data validation failed."""

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        error_details = details or {}
        if field:
            error_details["field"] = field
        
        super().__init__(message, "VALIDATION_ERROR", error_details)


class ConflictError(StoryHealAIServiceException):
    """Resource conflict."""

    def __init__(
        self,
        message: str,
        resource: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        error_details = details or {}
        if resource:
            error_details["resource_type"] = resource
        
        code = f"{resource.upper()}_CONFLICT" if resource else "CONFLICT"
        super().__init__(message, code, error_details)


class DatabaseError(StoryHealAIServiceException):
    """Database operation failed."""

    def __init__(
        self,
        message: str = "Database operation failed",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, "DATABASE_ERROR", details)


class ExternalServiceError(StoryHealAIServiceException):
    """External service call failed."""

    def __init__(
        self,
        service: str,
        message: str = "External service call failed",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        error_details = details or {}
        error_details["service"] = service
        
        super().__init__(message, "EXTERNAL_SERVICE_ERROR", error_details)


class RateLimitError(StoryHealAIServiceException):
    """Rate limit exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, "RATE_LIMIT_EXCEEDED", details)
