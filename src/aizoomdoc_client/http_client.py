"""
HTTP клиент с поддержкой авторизации и авто-refresh токенов.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, AsyncIterator, Iterator
from pathlib import Path

import httpx
from httpx_sse import connect_sse, aconnect_sse

from aizoomdoc_client.config import ConfigManager, get_config_manager
from aizoomdoc_client.exceptions import (
    AuthenticationError,
    TokenExpiredError,
    APIError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from aizoomdoc_client.models import TokenExchangeResponse, StreamEvent

logger = logging.getLogger(__name__)


class HTTPClient:
    """
    HTTP клиент для работы с AIZoomDoc Server.
    
    Поддерживает:
    - Авторизацию по static token
    - Автоматическое добавление Authorization header
    - Обработку ошибок API
    - SSE стриминг
    """
    
    DEFAULT_TIMEOUT = 60.0
    
    def __init__(
        self,
        server_url: Optional[str] = None,
        static_token: Optional[str] = None,
        config_manager: Optional[ConfigManager] = None,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """
        Инициализация HTTP клиента.
        
        Args:
            server_url: URL сервера. Если не указан, берётся из конфигурации.
            static_token: Статичный токен для авторизации.
            config_manager: Менеджер конфигурации.
            timeout: Таймаут запросов в секундах.
        """
        self.config_manager = config_manager or get_config_manager()
        
        if server_url:
            self.config_manager.set_server_url(server_url)
        
        self._static_token = static_token
        self.timeout = timeout
        
        # HTTP клиент
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
    
    @property
    def server_url(self) -> str:
        """Получить URL сервера."""
        return self.config_manager.get_config().server_url
    
    @property
    def is_authenticated(self) -> bool:
        """Проверить, авторизован ли клиент."""
        return self.config_manager.is_token_valid()
    
    def _get_sync_client(self) -> httpx.Client:
        """Получить синхронный HTTP клиент."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.server_url,
                timeout=self.timeout
            )
        return self._client
    
    async def _get_async_client(self) -> httpx.AsyncClient:
        """Получить асинхронный HTTP клиент."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=self.timeout
            )
        return self._async_client
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Получить заголовки авторизации."""
        token_data = self.config_manager.get_token()
        if token_data is None:
            return {}
        
        return {"Authorization": f"Bearer {token_data.access_token}"}
    
    def _handle_response_error(self, response: httpx.Response) -> None:
        """
        Обработать ошибку ответа.
        
        Args:
            response: HTTP ответ
        
        Raises:
            APIError: При ошибке API
        """
        if response.is_success:
            return
        
        try:
            error_data = response.json()
            error_type = error_data.get("error", "unknown_error")
            message = error_data.get("message", response.text)
            details = error_data.get("details")
        except Exception:
            error_type = "unknown_error"
            message = response.text or f"HTTP {response.status_code}"
            details = None
        
        if response.status_code == 401:
            raise AuthenticationError(message, details)
        elif response.status_code == 404:
            raise NotFoundError(message, details)
        elif response.status_code in (400, 422):
            raise ValidationError(message, details)
        elif response.status_code >= 500:
            raise ServerError(message, details)
        else:
            raise APIError(message, response.status_code, error_type, details)
    
    def authenticate(self, static_token: Optional[str] = None) -> TokenExchangeResponse:
        """
        Авторизоваться по статичному токену.
        
        Args:
            static_token: Статичный токен. Если не указан, используется сохранённый.
        
        Returns:
            Ответ с JWT токеном и информацией о пользователе
        
        Raises:
            AuthenticationError: При ошибке авторизации
        """
        token = static_token or self._static_token
        if not token:
            raise AuthenticationError("Static token is required for authentication")
        
        self._static_token = token
        
        client = self._get_sync_client()
        
        response = client.post(
            "/auth/exchange",
            json={"static_token": token}
        )
        
        self._handle_response_error(response)
        
        data = response.json()
        result = TokenExchangeResponse(**data)
        
        # Сохранить токен
        expires_at = datetime.utcnow() + timedelta(seconds=result.expires_in)
        self.config_manager.set_token(
            access_token=result.access_token,
            expires_at=expires_at,
            user_id=str(result.user.id),
            username=result.user.username
        )
        
        logger.info(f"Authenticated as {result.user.username}")
        return result
    
    def _ensure_authenticated(self) -> None:
        """
        Убедиться, что клиент авторизован.
        
        При истечении токена пытается переавторизоваться.
        
        Raises:
            TokenExpiredError: Если токен истёк и нет static_token
        """
        if self.is_authenticated:
            return
        
        # Попробовать переавторизоваться
        if self._static_token:
            self.authenticate(self._static_token)
            return
        
        raise TokenExpiredError(
            "Access token expired. Please authenticate again."
        )
    
    def request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        require_auth: bool = True
    ) -> httpx.Response:
        """
        Выполнить HTTP запрос.
        
        Args:
            method: HTTP метод (GET, POST, PATCH, DELETE)
            path: Путь API
            json: JSON тело запроса
            params: Query параметры
            files: Файлы для загрузки
            data: Form data
            require_auth: Требуется ли авторизация
        
        Returns:
            HTTP ответ
        
        Raises:
            APIError: При ошибке API
        """
        if require_auth:
            self._ensure_authenticated()
        
        client = self._get_sync_client()
        headers = self._get_auth_headers() if require_auth else {}
        
        response = client.request(
            method,
            path,
            json=json,
            params=params,
            files=files,
            data=data,
            headers=headers
        )
        
        # При 401 пробуем переавторизоваться и повторить
        if response.status_code == 401 and require_auth and self._static_token:
            logger.info("Token expired, re-authenticating...")
            self.authenticate(self._static_token)
            
            headers = self._get_auth_headers()
            response = client.request(
                method,
                path,
                json=json,
                params=params,
                files=files,
                data=data,
                headers=headers
            )
        
        self._handle_response_error(response)
        return response
    
    def get(self, path: str, **kwargs) -> httpx.Response:
        """GET запрос."""
        return self.request("GET", path, **kwargs)
    
    def post(self, path: str, **kwargs) -> httpx.Response:
        """POST запрос."""
        return self.request("POST", path, **kwargs)
    
    def patch(self, path: str, **kwargs) -> httpx.Response:
        """PATCH запрос."""
        return self.request("PATCH", path, **kwargs)
    
    def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETE запрос."""
        return self.request("DELETE", path, **kwargs)
    
    def stream_sse(
        self,
        path: str,
        *,
        method: str = "GET",
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Iterator[StreamEvent]:
        """
        Стриминг SSE событий.
        
        Args:
            path: Путь API
            method: HTTP метод
            json: JSON тело запроса
            params: Query параметры
        
        Yields:
            StreamEvent
        """
        self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        
        with httpx.Client(
            base_url=self.server_url,
            timeout=httpx.Timeout(timeout=300.0)  # Длинный таймаут для стриминга
        ) as client:
            with connect_sse(
                client,
                method,
                path,
                json=json,
                params=params,
                headers=headers
            ) as event_source:
                for sse in event_source.iter_sse():
                    try:
                        import json as json_module
                        data = json_module.loads(sse.data) if sse.data else {}
                        
                        # Отладка: выводим все SSE события
                        print(f"[HTTP SSE] event={sse.event}, data_keys={list(data.keys()) if data else []}", flush=True)
                        
                        yield StreamEvent(
                            event=sse.event or "message",
                            data=data,
                            timestamp=datetime.utcnow()
                        )
                        
                        # Завершаем при completed или error
                        if sse.event in ("completed", "error"):
                            break
                            
                    except Exception as e:
                        logger.warning(f"Failed to parse SSE event: {e}")
                        print(f"[HTTP SSE ERROR] {e}", flush=True)
                        continue
    
    def upload_file(self, path: str, file_path: Path) -> httpx.Response:
        """
        Загрузить файл.
        
        Args:
            path: Путь API
            file_path: Путь к локальному файлу
        
        Returns:
            HTTP ответ
        """
        self._ensure_authenticated()
        
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f)}
            return self.post(path, files=files)
    
    def logout(self) -> None:
        """Выйти из системы."""
        try:
            self.post("/auth/logout", require_auth=False)
        except Exception:
            pass  # Игнорируем ошибки при logout
        
        self.config_manager.clear_all()
        logger.info("Logged out")
    
    def clear_tokens(self) -> None:
        """Очистить сохранённые токены."""
        self.config_manager.clear_token()
    
    def close(self) -> None:
        """Закрыть HTTP клиент."""
        if self._client:
            self._client.close()
            self._client = None
        
        if self._async_client:
            # Для асинхронного клиента нужен отдельный close
            pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


