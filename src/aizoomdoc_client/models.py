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
    # LLM параметры
    temperature: float = Field(default=1.0, description="Температура генерации (0.0-2.0)")
    top_p: float = Field(default=0.95, description="Top-p sampling (0.0-1.0)")
    thinking_enabled: bool = Field(default=True, description="Режим thinking (deep think)")
    thinking_budget: int = Field(default=0, description="Бюджет токенов для thinking (0=авто)")
    media_resolution: Literal["low", "medium", "high"] = Field(default="high", description="Разрешение медиа")


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


class MessageImage(BaseModel):
    """Изображение в сообщении."""
    id: UUID
    file_id: Optional[UUID] = None
    image_type: Optional[str] = None
    description: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    url: Optional[str] = None


class MessageResponse(BaseModel):
    """Ответ с сообщением."""
    id: UUID
    chat_id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    message_type: str = "text"
    created_at: datetime
    images: List[MessageImage] = []


class ChatHistoryResponse(BaseModel):
    """История чата."""
    chat: ChatResponse
    messages: List[MessageResponse]


# ===== STREAMING MODELS =====

# Известные типы событий для подсказок IDE
KNOWN_EVENT_TYPES = [
    "phase_started",
    "phase_progress",
    "llm_token",
    "llm_thinking",
    "llm_final",
    "tool_call",
    "image_ready",
    "error",
    "completed",
    # Дополнительные события от сервера
    "queue_position",
    "processing_started",
    "message",
]


class StreamEvent(BaseModel):
    """Событие стриминга."""
    # Используем str вместо Literal для совместимости с новыми типами событий от сервера
    event: str
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


class GoogleFileUploadResponse(BaseModel):
    """Ответ после загрузки файла в Google File API."""
    id: Optional[UUID] = None
    filename: str
    mime_type: str
    size_bytes: int
    google_file_uri: str
    google_file_name: str
    state: str = "ACTIVE"
    storage_path: Optional[str] = None


# ===== PROJECTS TREE MODELS (read-only) =====

class JobFileInfo(BaseModel):
    """Информация о файле из job_files."""
    id: UUID
    job_id: UUID
    file_type: str  # result_md, ocr_html
    r2_key: str
    file_name: str
    file_size: Optional[int] = 0
    created_at: datetime


class TreeNode(BaseModel):
    """Узел дерева проектов."""
    id: UUID
    parent_id: Optional[UUID] = None
    client_id: Optional[str] = None
    node_type: str
    name: str
    code: Optional[str] = None
    version: Optional[int] = None
    status: str = "active"
    attributes: Dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
    files: List["JobFileInfo"] = Field(default_factory=list, description="Файлы результатов (MD, HTML)")


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
    data_dir: Optional[str] = Field(
        default=None,
        description="Папка для локальных данных (логи чатов, изображения). None = ~/.aizoomdoc/data"
    )

