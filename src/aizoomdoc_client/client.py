"""
Основной клиент AIZoomDoc.

Предоставляет высокоуровневый API для работы с сервером.
"""

import logging
from pathlib import Path
from typing import Optional, List, Iterator, Literal
from uuid import UUID

from aizoomdoc_client.config import ConfigManager, get_config_manager
from aizoomdoc_client.http_client import HTTPClient
from aizoomdoc_client.models import (
    UserInfo,
    UserSettings,
    UserMeResponse,
    ChatResponse,
    ChatHistoryResponse,
    MessageResponse,
    StreamEvent,
    FileUploadResponse,
    FileInfo,
    TreeNode,
    PromptUserRole,
    TokenExchangeResponse,
)
from aizoomdoc_client.exceptions import (
    AIZoomDocError,
    AuthenticationError,
)

logger = logging.getLogger(__name__)


class AIZoomDocClient:
    """
    Клиент для работы с AIZoomDoc Server.
    
    Пример использования:
    
    ```python
    client = AIZoomDocClient(
        server_url="http://localhost:8000",
        static_token="your-token"
    )
    
    # Авторизация (автоматически при первом запросе)
    client.authenticate()
    
    # Создание чата
    chat = client.create_chat(title="Мой чат")
    
    # Отправка сообщения со стримингом
    for event in client.send_message(chat.id, "Какое оборудование?"):
        if event.event == "llm_token":
            print(event.data["token"], end="", flush=True)
    ```
    """
    
    def __init__(
        self,
        server_url: Optional[str] = None,
        static_token: Optional[str] = None,
        config_dir: Optional[Path] = None,
        timeout: float = 60.0
    ):
        """
        Инициализация клиента.
        
        Args:
            server_url: URL сервера (например, http://localhost:8000)
            static_token: Статичный токен для авторизации
            config_dir: Директория для хранения конфигурации
            timeout: Таймаут запросов в секундах
        """
        self._config_manager = get_config_manager(config_dir)
        
        self._http = HTTPClient(
            server_url=server_url,
            static_token=static_token,
            config_manager=self._config_manager,
            timeout=timeout
        )
    
    # ===== AUTHENTICATION =====
    
    def authenticate(self, static_token: Optional[str] = None) -> TokenExchangeResponse:
        """
        Авторизоваться по статичному токену.
        
        Args:
            static_token: Статичный токен (если не передан при создании)
        
        Returns:
            Информация о токене и пользователе
        
        Raises:
            AuthenticationError: При ошибке авторизации
        """
        return self._http.authenticate(static_token)
    
    @property
    def is_authenticated(self) -> bool:
        """Проверить, авторизован ли клиент."""
        return self._http.is_authenticated
    
    def logout(self) -> None:
        """Выйти из системы."""
        self._http.logout()
    
    def clear_tokens(self) -> None:
        """Очистить сохранённые токены."""
        self._http.clear_tokens()
    
    # ===== USER & SETTINGS =====
    
    def get_me(self) -> UserMeResponse:
        """
        Получить информацию о текущем пользователе.
        
        Returns:
            Пользователь, настройки и флаг наличия Gemini API key
        """
        response = self._http.get("/me")
        return UserMeResponse(**response.json())
    
    def update_settings(
        self,
        model_profile: Optional[Literal["simple", "complex"]] = None,
        selected_role_prompt_id: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        thinking_enabled: Optional[bool] = None,
        thinking_budget: Optional[int] = None,
        media_resolution: Optional[Literal["low", "medium", "high"]] = None
    ) -> UserSettings:
        """
        Обновить настройки пользователя.
        
        Args:
            model_profile: Режим модели ("simple" или "complex")
            selected_role_prompt_id: ID выбранной роли (int)
            temperature: Температура генерации (0.0-2.0)
            top_p: Top-p sampling (0.0-1.0)
            thinking_enabled: Включить режим thinking
            thinking_budget: Бюджет токенов для thinking (0=авто)
            media_resolution: Разрешение медиа ("low", "medium", "high")
        
        Returns:
            Обновлённые настройки
        """
        data = {}
        if model_profile is not None:
            data["model_profile"] = model_profile
        if selected_role_prompt_id is not None:
            data["selected_role_prompt_id"] = selected_role_prompt_id
        if temperature is not None:
            data["temperature"] = temperature
        if top_p is not None:
            data["top_p"] = top_p
        if thinking_enabled is not None:
            data["thinking_enabled"] = thinking_enabled
        if thinking_budget is not None:
            data["thinking_budget"] = thinking_budget
        if media_resolution is not None:
            data["media_resolution"] = media_resolution
        
        response = self._http.patch("/me/settings", json=data)
        return UserSettings(**response.json())
    
    def get_available_roles(self) -> List[PromptUserRole]:
        """
        Получить список доступных ролей.
        
        Returns:
            Список ролей
        """
        response = self._http.get("/prompts/roles")
        data = response.json()
        return [PromptUserRole(**role) for role in data]
    
    # ===== CHATS =====
    
    def create_chat(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> ChatResponse:
        """
        Создать новый чат.
        
        Args:
            title: Заголовок чата
            description: Описание
        
        Returns:
            Созданный чат
        """
        data = {}
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        
        response = self._http.post("/chats", json=data)
        chat = ChatResponse(**response.json())
        
        # Установить как активный чат
        self._config_manager.set_active_chat(chat.id)
        
        return chat
    
    def get_chat(self, chat_id: UUID) -> ChatResponse:
        """
        Получить информацию о чате.
        
        Args:
            chat_id: ID чата
        
        Returns:
            Чат
        """
        response = self._http.get(f"/chats/{chat_id}")
        return ChatResponse(**response.json())
    
    def get_chat_history(self, chat_id: UUID) -> ChatHistoryResponse:
        """
        Получить историю чата с сообщениями.
        
        Args:
            chat_id: ID чата
        
        Returns:
            Чат с историей сообщений
        """
        response = self._http.get(f"/chats/{chat_id}")
        return ChatHistoryResponse(**response.json())
    
    def list_chats(self, limit: int = 50) -> List[ChatResponse]:
        """
        Получить список чатов пользователя.
        
        Args:
            limit: Максимальное количество чатов
        
        Returns:
            Список чатов
        """
        response = self._http.get("/chats", params={"limit": limit})
        data = response.json()
        return [ChatResponse(**chat) for chat in data]
    
    def delete_chat(self, chat_id: UUID) -> bool:
        """
        Удалить чат (асинхронно на сервере).
        
        Сервер запускает каскадное удаление в фоне:
        - Файлы из R2
        - Логи сервера
        - Записи БД
        
        Клиент должен отдельно удалить локальные файлы.
        
        Args:
            chat_id: ID чата
        
        Returns:
            True если удаление запланировано (202 Accepted)
        """
        try:
            response = self._http.delete(f"/chats/{chat_id}")
            return response.status_code == 202
        except Exception as e:
            logger.error(f"Error deleting chat {chat_id}: {e}")
            return False
    
    def use_chat(self, chat_id: UUID) -> ChatResponse:
        """
        Установить чат как активный.
        
        Args:
            chat_id: ID чата
        
        Returns:
            Чат
        """
        chat = self.get_chat(chat_id)
        self._config_manager.set_active_chat(chat.id)
        return chat
    
    def get_active_chat_id(self) -> Optional[UUID]:
        """
        Получить ID активного чата.
        
        Returns:
            ID чата или None
        """
        return self._config_manager.get_active_chat()
    
    # ===== MESSAGES =====
    
    def send_message(
        self,
        chat_id: UUID,
        message: str,
        attached_file_ids: Optional[List[UUID]] = None,
        attached_document_ids: Optional[List[UUID]] = None,
        client_id: Optional[str] = None,
        google_files: Optional[List[dict]] = None,
        tree_files: Optional[List[dict]] = None,
        compare_document_ids_a: Optional[List[UUID]] = None,
        compare_document_ids_b: Optional[List[UUID]] = None
    ) -> Iterator[StreamEvent]:
        """
        Отправить сообщение в чат со стримингом ответа.

        Args:
            chat_id: ID чата
            message: Текст сообщения
            attached_file_ids: ID прикреплённых файлов
            attached_document_ids: ID документов из дерева проектов
            client_id: ID клиента
            google_files: Файлы из Google File API [{uri, mime_type}]
            tree_files: Файлы MD/HTML из дерева [{r2_key, file_type}]
            compare_document_ids_a: ID документов для группы A (режим сравнения)
            compare_document_ids_b: ID документов для группы B (режим сравнения)

        Yields:
            События стриминга (фазы, токены LLM, ошибки)

        Example:
            ```python
            for event in client.send_message(chat.id, "Вопрос"):
                if event.event == "llm_token":
                    print(event.data["token"], end="", flush=True)
                elif event.event == "phase_started":
                    print(f"[{event.data['phase']}]")
            ```
        """
        data = {"content": message}
        if attached_file_ids:
            data["attached_file_ids"] = [str(fid) for fid in attached_file_ids]
        if attached_document_ids:
            data["attached_document_ids"] = [str(did) for did in attached_document_ids]
        if google_files:
            data["google_files"] = google_files
        if tree_files:
            data["tree_files"] = tree_files

        # Отправляем сообщение
        response = self._http.post(f"/chats/{chat_id}/messages", json=data)

        # Стримим события
        params = {}
        if client_id:
            params["client_id"] = client_id
        if attached_document_ids:
            params["document_ids"] = [str(did) for did in attached_document_ids]
        if google_files:
            import json
            params["google_files"] = json.dumps(google_files)
        if tree_files:
            import json
            params["tree_files"] = json.dumps(tree_files)
        if compare_document_ids_a:
            params["compare_document_ids_a"] = [str(did) for did in compare_document_ids_a]
        if compare_document_ids_b:
            params["compare_document_ids_b"] = [str(did) for did in compare_document_ids_b]

        yield from self._http.stream_sse(
            f"/chats/{chat_id}/stream",
            method="GET",
            params=params
        )
    
    def send_message_sync(
        self,
        chat_id: UUID,
        message: str,
        attached_file_ids: Optional[List[UUID]] = None,
        attached_document_ids: Optional[List[UUID]] = None,
        client_id: Optional[str] = None
    ) -> MessageResponse:
        """
        Отправить сообщение и дождаться полного ответа (без стриминга).
        
        Args:
            chat_id: ID чата
            message: Текст сообщения
            attached_file_ids: ID прикреплённых файлов
        
        Returns:
            Ответное сообщение от ассистента
        """
        data = {"content": message}
        if attached_file_ids:
            data["attached_file_ids"] = [str(fid) for fid in attached_file_ids]
        if attached_document_ids:
            data["attached_document_ids"] = [str(did) for did in attached_document_ids]
        
        response = self._http.post(f"/chats/{chat_id}/messages", json=data)
        
        # Собираем полный ответ из стриминга
        full_response = ""
        params = {}
        if client_id:
            params["client_id"] = client_id
        if attached_document_ids:
            params["document_ids"] = [str(did) for did in attached_document_ids]

        for event in self._http.stream_sse(f"/chats/{chat_id}/stream", params=params):
            if event.event == "llm_token":
                full_response += event.data.get("token", "")
            elif event.event == "llm_final":
                full_response = event.data.get("content", full_response)
            elif event.event == "error":
                raise AIZoomDocError(
                    event.data.get("message", "Unknown error"),
                    event.data
                )
        
        # Получаем последнее сообщение из истории
        history = self.get_chat_history(chat_id)
        if history.messages:
            return history.messages[-1]
        
        # Fallback - создаём объект из стриминга
        from datetime import datetime
        return MessageResponse(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            chat_id=chat_id,
            role="assistant",
            content=full_response,
            message_type="text",
            created_at=datetime.utcnow()
        )
    
    # ===== FILES =====
    
    def upload_file(self, file_path: str | Path) -> FileUploadResponse:
        """
        Загрузить файл на сервер.
        
        Args:
            file_path: Путь к файлу
        
        Returns:
            Информация о загруженном файле
        """
        path = Path(file_path)
        if not path.exists():
            raise AIZoomDocError(f"File not found: {path}")
        
        response = self._http.upload_file("/files/upload", path)
        return FileUploadResponse(**response.json())
    
    def upload_file_for_llm(self, file_path: str | Path) -> "GoogleFileUploadResponse":
        """
        Загрузить файл через Google File API для использования в LLM.
        
        Args:
            file_path: Путь к файлу (MD, HTML, TXT, PDF, изображения)
        
        Returns:
            Информация о файле с Google File URI
        """
        from aizoomdoc_client.models import GoogleFileUploadResponse
        
        path = Path(file_path)
        if not path.exists():
            raise AIZoomDocError(f"File not found: {path}")
        
        response = self._http.upload_file("/files/upload-for-llm", path)
        return GoogleFileUploadResponse(**response.json())
    
    def get_file(self, file_id: UUID) -> FileInfo:
        """
        Получить информацию о файле.
        
        Args:
            file_id: ID файла
        
        Returns:
            Информация о файле
        """
        response = self._http.get(f"/files/{file_id}")
        return FileInfo(**response.json())
    
    # ===== PROJECTS TREE (read-only) =====
    
    def get_projects_tree(
        self,
        client_id: Optional[str] = None,
        parent_id: Optional[UUID] = None,
        all_nodes: bool = False,
        include_files: bool = False
    ) -> List[TreeNode]:
        """
        Получить дерево проектов.

        Args:
            client_id: ID клиента (организации)
            parent_id: ID родительского узла
            all_nodes: Получить все узлы (для построения дерева на клиенте)
            include_files: Включить файлы результатов (MD, HTML) из job_files

        Returns:
            Список узлов дерева
        """
        params = {}
        if client_id:
            params["client_id"] = client_id
        if parent_id:
            params["parent_id"] = str(parent_id)
        if all_nodes:
            params["all_nodes"] = "true"
        if include_files:
            params["include_files"] = "true"

        response = self._http.get("/projects/tree", params=params)
        data = response.json()
        return [TreeNode(**node) for node in data]
    
    def get_document_results(self, document_node_id: UUID) -> List[FileInfo]:
        """
        Получить результаты обработки документа.
        
        Args:
            document_node_id: ID узла документа
        
        Returns:
            Список файлов результатов (MD, HTML, JSON, кропы)
        """
        response = self._http.get(f"/projects/documents/{document_node_id}/results")
        data = response.json()
        return [FileInfo(**f) for f in data.get("files", [])]
    
    def search_documents(
        self,
        query: str,
        client_id: Optional[str] = None,
        limit: int = 10
    ) -> List[TreeNode]:
        """
        Поиск документов.
        
        Args:
            query: Поисковый запрос
            client_id: ID клиента
            limit: Максимальное количество результатов
        
        Returns:
            Список найденных документов
        """
        params = {"q": query, "limit": limit}
        if client_id:
            params["client_id"] = client_id
        
        response = self._http.get("/projects/search", params=params)
        data = response.json()
        return [TreeNode(**node) for node in data]
    
    # ===== CONTEXT MANAGEMENT =====
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._http.close()
    
    def close(self) -> None:
        """Закрыть клиент."""
        self._http.close()

