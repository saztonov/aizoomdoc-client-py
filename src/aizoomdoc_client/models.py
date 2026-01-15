"""
Pydantic модели для API клиента.

Эти модели соответствуют контрактам aizoomdoc-server.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field


# ===== AUTH MODELS =====

class UserInfo(BaseModel):
    """Информация о пользователе."""
    id: UUID
    username: str
    status: str = Field(default="active")
    created_at: datetime


class TokenExchangeResponse(BaseModel):
    """Ответ с JWT токенами."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo


# ===== SETTINGS MODELS =====

class UserSettings(BaseModel):
    """Настройки пользователя."""
    model_profile: Literal["simple", "complex"] = Field(
        default="simple",
        description="Режим модели: simple (flash) или complex (flash+pro)"
    )
    selected_role_prompt_id: Optional[int] = Field(
        default=None,
        description="ID выбранной роли из prompts_user (bigint)"
    )


class UserMeResponse(BaseModel):
    """Ответ с информацией о текущем пользователе."""
    user: UserInfo
    settings: UserSettings
    gemini_api_key_configured: bool


# ===== PROMPTS MODELS =====

class PromptUserRole(BaseModel):
    """Пользовательский промпт-роль."""
    id: int  # bigint в БД
    name: str
    content: str
    description: Optional[str] = None
    is_active: bool = True
    version: int = 1
    created_at: datetime
    updated_at: datetime


# ===== CHAT MODELS =====

class ChatResponse(BaseModel):
    """Ответ с информацией о чате."""
    id: UUID
    title: str
    description: Optional[str] = None
    user_id: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """Ответ с сообщением."""
    id: UUID
    chat_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: str = "text"
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """История чата."""
    chat: ChatResponse
    messages: List[MessageResponse]


# ===== STREAMING MODELS =====

class StreamEvent(BaseModel):
    """Событие стриминга."""
    event: Literal[
        "phase_started",
        "phase_progress",
        "llm_token",
        "llm_final",
        "tool_call",
        "error",
        "completed"
    ]
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[datetime] = None


class PhaseStartedData(BaseModel):
    """Данные события начала фазы."""
    phase: str
    description: str


class PhaseProgressData(BaseModel):
    """Данные события прогресса."""
    phase: str
    progress: float
    message: str


class LLMTokenData(BaseModel):
    """Данные токена от LLM."""
    token: str
    accumulated: str = ""


class ToolCallData(BaseModel):
    """Данные вызова инструмента."""
    tool: Literal["request_images", "zoom", "request_documents"]
    parameters: Dict[str, Any]
    reason: str


# ===== FILE MODELS =====

class FileInfo(BaseModel):
    """Информация о файле."""
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    source_type: Optional[str] = None
    storage_path: Optional[str] = None
    external_url: Optional[str] = None
    created_at: datetime


class FileUploadResponse(BaseModel):
    """Ответ после загрузки файла."""
    id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime


# ===== PROJECTS TREE MODELS (read-only) =====

class TreeNode(BaseModel):
    """Узел дерева проектов."""
    id: UUID
    parent_id: Optional[UUID] = None
    client_id: str
    node_type: str
    name: str
    code: Optional[str] = None
    version: Optional[int] = None
    status: str = "active"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentResults(BaseModel):
    """Результаты обработки документа."""
    document_node_id: UUID
    files: List[FileInfo]


# ===== ERROR MODELS =====

class ErrorResponse(BaseModel):
    """Ответ с ошибкой."""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# ===== LOCAL CONFIG MODELS =====

class TokenData(BaseModel):
    """Данные хранения токенов локально."""
    access_token: str
    expires_at: datetime
    user_id: str
    username: str


class ClientConfig(BaseModel):
    """Конфигурация клиента."""
    server_url: str
    token_data: Optional[TokenData] = None
    active_chat_id: Optional[UUID] = None

