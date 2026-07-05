class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


class MangabaError(Exception):
    """Base exception for all Mangaba Operator errors"""


class TokenLimitExceeded(MangabaError):
    """Exception raised when the token limit is exceeded"""


class ContextWindowExceeded(MangabaError):
    """Prompt maior que a janela de contexto do provedor.

    Erro PERMANENTE: não deve ser retryado — o agente reage encolhendo o
    histórico e repetindo o passo."""
