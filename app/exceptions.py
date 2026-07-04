class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


class MangabaError(Exception):
    """Base exception for all Mangaba AI errors"""


class TokenLimitExceeded(MangabaError):
    """Exception raised when the token limit is exceeded"""
