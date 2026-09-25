"""
Domain error hierarchy.

What it does:
- Defines strongly typed, domain-specific exception classes.
- Standardizes error signaling across application boundaries.

What it does NOT do:
- Does NOT format HTTP or Discord responses.
- Does NOT perform logging.
"""

class AppError(Exception):
    """Base error for all application domain exceptions."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class NotFoundError(AppError):
    """Raised when a requested domain entity is not found."""
    pass

class ValidationError(AppError):
    """Raised when entity data or input fails business validation."""
    pass

class TaskAlreadyCompletedError(AppError):
    """Raised when attempting to complete a task that has already finished."""
    pass

class DeadlineAlreadyCompletedError(AppError):
    """Raised when attempting to complete a deadline that has already finished."""
    pass

class StorageError(AppError):
    """Raised when an error occurs during file or persistence operations."""
    pass
