class AIServiceError(Exception):
    """Base error for AI service operations."""


class AIConfigurationError(AIServiceError):
    """Raised when AI provider settings are missing or invalid."""


class AITaskNotFoundError(AIServiceError):
    """Raised when an unknown task name is requested."""


class AITaskError(AIServiceError):
    """Raised when a task fails to produce a result."""
