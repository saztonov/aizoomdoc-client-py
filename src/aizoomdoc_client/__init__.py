"""
AIZoomDoc Python Client.

Локальный клиент для работы с AIZoomDoc Server.
"""

from aizoomdoc_client.client import AIZoomDocClient
from aizoomdoc_client.models import (
    UserInfo,
    UserSettings,
    ChatResponse,
    MessageResponse,
    StreamEvent,
    FileInfo,
    TreeNode,
    PromptUserRole,
)
from aizoomdoc_client.exceptions import (
    AIZoomDocError,
    AuthenticationError,
    TokenExpiredError,
    APIError,
    NotFoundError,
    ServerError,
)

__version__ = "2.0.0"

__all__ = [
    # Client
    "AIZoomDocClient",
    # Models
    "UserInfo",
    "UserSettings",
    "ChatResponse",
    "MessageResponse",
    "StreamEvent",
    "FileInfo",
    "TreeNode",
    "PromptUserRole",
    # Exceptions
    "AIZoomDocError",
    "AuthenticationError",
    "TokenExpiredError",
    "APIError",
    "NotFoundError",
    "ServerError",
]

