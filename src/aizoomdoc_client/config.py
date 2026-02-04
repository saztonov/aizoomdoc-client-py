"""
Управление конфигурацией и хранением токенов.

Хранит данные в файле в домашней директории пользователя.
"""

import json
import os
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID

from aizoomdoc_client.models import ClientConfig, TokenData

logger = logging.getLogger(__name__)

# =============================================================================
# ВСТРОЕННЫЕ НАСТРОЙКИ ДЛЯ PRODUCTION
# =============================================================================
# Эти значения используются для автоматического подключения к серверу
# при первом запуске exe-клиента без необходимости ручной настройки
DEFAULT_SERVER_URL = "https://osa.fvds.ru"
DEFAULT_STATIC_TOKEN = "dev-static-token-default-user"

# Известные серверы для быстрого переключения
KNOWN_SERVERS = {
    "production": "https://osa.fvds.ru",
    "local": "http://localhost:8000"
}
# =============================================================================


class ConfigManager:
    """Менеджер конфигурации клиента."""
    
    # Директория для хранения конфигурации
    CONFIG_DIR_NAME = ".aizoomdoc"
    CONFIG_FILE_NAME = "config.json"
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Инициализация менеджера конфигурации.
        
        Args:
            config_dir: Путь к директории конфигурации.
                        По умолчанию ~/.aizoomdoc/
        """
        if config_dir is None:
            home = Path.home()
            self.config_dir = home / self.CONFIG_DIR_NAME
        else:
            self.config_dir = config_dir
        
        self.config_file = self.config_dir / self.CONFIG_FILE_NAME
        self._config: Optional[ClientConfig] = None
    
    def _ensure_config_dir(self) -> None:
        """Создать директорию конфигурации если не существует."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load(self) -> ClientConfig:
        """
        Загрузить конфигурацию из файла.
        
        Returns:
            Конфигурация клиента
        """
        if self._config is not None:
            return self._config
        
        if not self.config_file.exists():
            # Конфигурация по умолчанию
            self._config = ClientConfig(
                server_url=DEFAULT_SERVER_URL,
                token_data=None,
                active_chat_id=None,
                data_dir=None
            )
            return self._config
        
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Парсим token_data если есть
            if data.get("token_data"):
                data["token_data"]["expires_at"] = datetime.fromisoformat(
                    data["token_data"]["expires_at"]
                )
                data["token_data"] = TokenData(**data["token_data"])
            
            # Парсим active_chat_id если есть
            if data.get("active_chat_id"):
                data["active_chat_id"] = UUID(data["active_chat_id"])
            
            self._config = ClientConfig(**data)
            return self._config
            
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            # Поврежденный файл - создаём новую конфигурацию
            self._config = ClientConfig(
                server_url=DEFAULT_SERVER_URL,
                token_data=None,
                active_chat_id=None,
                data_dir=None
            )
            return self._config
    
    def save(self, config: Optional[ClientConfig] = None) -> None:
        """
        Сохранить конфигурацию в файл.
        
        Args:
            config: Конфигурация для сохранения.
                   Если не указана, сохраняет текущую.
        """
        if config is not None:
            self._config = config
        
        if self._config is None:
            return
        
        self._ensure_config_dir()
        
        # Сериализация в JSON
        data = {
            "server_url": self._config.server_url,
            "token_data": None,
            "active_chat_id": str(self._config.active_chat_id) if self._config.active_chat_id else None,
            "data_dir": self._config.data_dir
        }
        
        if self._config.token_data:
            data["token_data"] = {
                "access_token": self._config.token_data.access_token,
                "expires_at": self._config.token_data.expires_at.isoformat(),
                "user_id": self._config.token_data.user_id,
                "username": self._config.token_data.username
            }
        
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def get_config(self) -> ClientConfig:
        """Получить текущую конфигурацию."""
        if self._config is None:
            return self.load()
        return self._config
    
    def set_server_url(self, url: str) -> None:
        """
        Установить URL сервера.
        
        Args:
            url: URL сервера (например, http://localhost:8000)
        """
        config = self.get_config()
        config.server_url = url.rstrip("/")
        self.save(config)
    
    def set_token(
        self,
        access_token: str,
        expires_at: datetime,
        user_id: str,
        username: str
    ) -> None:
        """
        Сохранить данные токена.
        
        Args:
            access_token: JWT access token
            expires_at: Время истечения токена
            user_id: ID пользователя
            username: Имя пользователя
        """
        config = self.get_config()
        config.token_data = TokenData(
            access_token=access_token,
            expires_at=expires_at,
            user_id=user_id,
            username=username
        )
        self.save(config)
    
    def clear_token(self) -> None:
        """Очистить данные токена."""
        config = self.get_config()
        config.token_data = None
        self.save(config)
    
    def get_token(self) -> Optional[TokenData]:
        """
        Получить данные токена.
        
        Returns:
            Данные токена или None если не авторизован
        """
        config = self.get_config()
        return config.token_data
    
    def is_token_valid(self) -> bool:
        """
        Проверить, валиден ли токен (не истёк).
        
        Returns:
            True если токен валиден
        """
        token_data = self.get_token()
        if token_data is None:
            return False
        
        # Добавляем запас в 60 секунд для refresh до истечения
        return token_data.expires_at > datetime.utcnow()
    
    def set_active_chat(self, chat_id: Optional[UUID]) -> None:
        """
        Установить активный чат.
        
        Args:
            chat_id: ID чата или None для сброса
        """
        config = self.get_config()
        config.active_chat_id = chat_id
        self.save(config)
    
    def get_active_chat(self) -> Optional[UUID]:
        """
        Получить ID активного чата.
        
        Returns:
            ID чата или None
        """
        config = self.get_config()
        return config.active_chat_id
    
    def clear_all(self) -> None:
        """Очистить всю конфигурацию (выход из системы)."""
        self._config = ClientConfig(
            server_url=self.get_config().server_url,
            token_data=None,
            active_chat_id=None,
            data_dir=self.get_config().data_dir
        )
        self.save()
    
    # ===== DATA DIR METHODS =====
    
    def set_data_dir(self, path: Optional[str]) -> None:
        """
        Установить папку для локальных данных.
        
        Args:
            path: Путь к папке или None для сброса к умолчанию
        """
        config = self.get_config()
        config.data_dir = path
        self.save(config)
    
    # ===== STATIC TOKEN METHODS =====
    
    def save_static_token(self, token: str, server_url: str) -> None:
        """
        Сохранить статичный токен в локальный файл.
        
        Файл сохраняется в папке данных (data_dir) для безопасного хранения.
        
        Args:
            token: Статичный токен
            server_url: URL сервера
        """
        try:
            data_dir = self.get_data_dir()
            token_file = data_dir / "credentials.json"
            
            credentials = {
                "static_token": token,
                "server_url": server_url,
                "saved_at": datetime.now().isoformat()
            }
            
            with open(token_file, "w", encoding="utf-8") as f:
                json.dump(credentials, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Static token saved to: {token_file}")
        except Exception as e:
            logger.error(f"Error saving static token: {e}")
    
    def load_static_token(self) -> Optional[Dict[str, str]]:
        """
        Загрузить статичный токен из локального файла.
        
        Returns:
            Dict с 'static_token' и 'server_url' или None если не найден
        """
        try:
            data_dir = self.get_data_dir()
            token_file = data_dir / "credentials.json"
            
            if not token_file.exists():
                return None
            
            with open(token_file, "r", encoding="utf-8") as f:
                credentials = json.load(f)
            
            if credentials.get("static_token") and credentials.get("server_url"):
                return {
                    "static_token": credentials["static_token"],
                    "server_url": credentials["server_url"]
                }
            return None
        except Exception as e:
            logger.error(f"Error loading static token: {e}")
            return None
    
    def clear_static_token(self) -> None:
        """Удалить сохранённый статичный токен."""
        try:
            data_dir = self.get_data_dir()
            token_file = data_dir / "credentials.json"

            if token_file.exists():
                token_file.unlink()
                logger.info("Static token file removed")
        except Exception as e:
            logger.error(f"Error clearing static token: {e}")

    def get_default_credentials(self) -> Optional[Dict[str, str]]:
        """
        Получить встроенные credentials для автоматического подключения.

        Используется когда нет сохранённых credentials и нужно
        автоматически подключиться к серверу при первом запуске.

        Returns:
            Dict с 'static_token' и 'server_url' или None если не заданы
        """
        if DEFAULT_STATIC_TOKEN and DEFAULT_SERVER_URL:
            return {
                "static_token": DEFAULT_STATIC_TOKEN,
                "server_url": DEFAULT_SERVER_URL
            }
        return None
    
    def get_data_dir(self) -> Path:
        """
        Получить папку для локальных данных.
        
        Returns:
            Path к папке данных (создаётся если не существует)
        """
        config = self.get_config()
        if config.data_dir:
            data_path = Path(config.data_dir)
        else:
            data_path = self.config_dir / "data"
        
        data_path.mkdir(parents=True, exist_ok=True)
        return data_path
    
    def get_chat_dir(self, chat_id: str) -> Path:
        """
        Получить папку для конкретного чата.
        
        Args:
            chat_id: ID чата
        
        Returns:
            Path к папке чата
        """
        chat_path = self.get_data_dir() / "chats" / chat_id
        chat_path.mkdir(parents=True, exist_ok=True)
        return chat_path
    
    def get_crops_dir(self, chat_id: str) -> Path:
        """
        Получить папку для изображений чата.
        
        Args:
            chat_id: ID чата
        
        Returns:
            Path к папке crops
        """
        crops_path = self.get_chat_dir(chat_id) / "crops"
        crops_path.mkdir(parents=True, exist_ok=True)
        return crops_path
    
    def delete_chat_data(self, chat_id: str) -> bool:
        """
        Удалить локальные данные чата.
        
        Удаляет папку {data_dir}/chats/{chat_id}/ со всем содержимым:
        - chat.log
        - full_dialog.log
        - crops/
        
        Args:
            chat_id: ID чата
        
        Returns:
            True если успешно удалено
        """
        import shutil
        
        try:
            data_dir = self.get_data_dir()
            chat_dir = data_dir / "chats" / chat_id
            
            if chat_dir.exists():
                shutil.rmtree(chat_dir)
                logger.info(f"Deleted local chat data: {chat_dir}")
                return True
            else:
                logger.debug(f"Chat directory not found: {chat_dir}")
                return True  # Нет данных - считаем успехом
        
        except Exception as e:
            logger.error(f"Error deleting chat data for {chat_id}: {e}")
            return False
    
    def save_chat_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        images: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Сохранить сообщение чата в лог-файл.
        
        Args:
            chat_id: ID чата
            role: Роль (user/assistant)
            content: Текст сообщения
            images: Список изображений (опционально)
        """
        try:
            chat_dir = self.get_chat_dir(chat_id)
            log_file = chat_dir / "chat.log"
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"[{timestamp}] {role.upper()}\n")
                f.write(f"{'='*60}\n")
                f.write(content)
                f.write("\n")
                
                if images:
                    f.write(f"\n--- Изображения ({len(images)}) ---\n")
                    for img in images:
                        img_type = img.get("image_type", "unknown")
                        url = img.get("url", "")
                        local_path = img.get("local_path", "")
                        f.write(f"  - {img_type}: {local_path or url}\n")
                
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
    
    def log_sse_event(
        self,
        chat_id: str,
        event_type: str,
        data: Dict[str, Any]
    ) -> None:
        """
        Записать SSE-событие в единый лог диалога.
        Формат читаемый для человека.

        Args:
            chat_id: ID чата
            event_type: Тип события (phase_started, tool_call, etc.)
            data: Данные события
        """
        try:
            chat_dir = self.get_chat_dir(chat_id)
            log_file = chat_dir / "dialog.log"

            timestamp = datetime.now().strftime("%H:%M:%S")

            # Разделители для читаемости
            THICK_LINE = "=" * 80
            THIN_LINE = "-" * 80

            with open(log_file, "a", encoding="utf-8") as f:

                if event_type == "user_request":
                    # Заголовок нового запроса пользователя
                    message = data.get("message", "")
                    docs = data.get("document_ids", [])
                    files = data.get("local_files", [])
                    tree_files = data.get("tree_files", [])
                    google_files = data.get("google_files", [])
                    compare_a = data.get("compare_document_ids_a", [])
                    compare_b = data.get("compare_document_ids_b", [])

                    f.write(f"\n{THICK_LINE}\n")
                    f.write(f"[{timestamp}] ZAPROS POLZOVATELYA\n")
                    f.write(f"{THICK_LINE}\n")
                    f.write(f"Soobschenie:\n    {message}\n")

                    if docs:
                        f.write(f"\nPrikreplennye dokumenty:\n")
                        for doc in docs:
                            f.write(f"    * {doc}\n")

                    if files:
                        f.write(f"\nLokalnye fajly:\n")
                        for file in files:
                            f.write(f"    * {file}\n")

                    if tree_files:
                        f.write(f"\nTree-fajly:\n")
                        for tf in tree_files:
                            r2_key = tf.get('r2_key', '') if isinstance(tf, dict) else str(tf)
                            file_type = tf.get('file_type', '') if isinstance(tf, dict) else ''
                            f.write(f"    * r2_key: {r2_key} (type: {file_type})\n")

                    if google_files:
                        f.write(f"\nGoogle Files:\n")
                        for gf in google_files:
                            uri = gf.get('uri', '') if isinstance(gf, dict) else str(gf)
                            mime = gf.get('mime_type', '') if isinstance(gf, dict) else ''
                            f.write(f"    * URI: {uri}\n")
                            if mime:
                                f.write(f"      MIME: {mime}\n")

                    if compare_a or compare_b:
                        f.write(f"\nRezhim sravneniya:\n")
                        f.write(f"    Dokumenty A: {compare_a}\n")
                        f.write(f"    Dokumenty B: {compare_b}\n")

                elif event_type == "file_uploaded":
                    filename = data.get("filename", "")
                    uri = data.get("uri", "")
                    mime_type = data.get("mime_type", "")
                    f.write(f"\n{THIN_LINE}\n")
                    f.write(f"[{timestamp}] FAJL ZAGRUZHEN\n")
                    f.write(f"{THIN_LINE}\n")
                    f.write(f"Fajl: {filename}\n")
                    f.write(f"URI: {uri}\n")
                    if mime_type:
                        f.write(f"MIME: {mime_type}\n")

                elif event_type == "phase_started":
                    phase = data.get("phase", "")
                    desc = data.get("description", "")
                    f.write(f"\n{THIN_LINE}\n")
                    f.write(f"[{timestamp}] FAZA: {phase}\n")
                    f.write(f"{THIN_LINE}\n")
                    if desc:
                        f.write(f"Opisanie: {desc}\n")

                elif event_type == "tool_call":
                    tool = data.get("tool", "unknown")
                    reason = data.get("reason", "")
                    params = data.get("parameters", {})
                    f.write(f"\n{THIN_LINE}\n")
                    f.write(f"[{timestamp}] VYZOV INSTRUMENTA: {tool}\n")
                    f.write(f"{THIN_LINE}\n")
                    if reason:
                        f.write(f"Prichina: {reason}\n")
                    if params:
                        f.write(f"Parametry:\n")
                        params_str = json.dumps(params, ensure_ascii=False, indent=4)
                        for line in params_str.split('\n'):
                            f.write(f"    {line}\n")

                elif event_type == "image_ready":
                    block_id = data.get("block_id", "")
                    kind = data.get("kind", "")
                    url = data.get("url") or data.get("public_url", "")
                    reason = data.get("reason", "")
                    bbox = data.get("bbox_norm") or data.get("bbox", [])
                    f.write(f"\n{THIN_LINE}\n")
                    f.write(f"[{timestamp}] IZOBRAZHENIE GOTOVO\n")
                    f.write(f"{THIN_LINE}\n")
                    f.write(f"Block ID: {block_id}\n")
                    f.write(f"Tip: {kind}\n")
                    f.write(f"URL: {url}\n")
                    if reason:
                        f.write(f"Prichina: {reason}\n")
                    if bbox:
                        f.write(f"BBox: {bbox}\n")

                elif event_type == "thinking" or event_type == "llm_thinking":
                    content = data.get("content", "")
                    if content:
                        f.write(f"\n{THIN_LINE}\n")
                        f.write(f"[{timestamp}] RAZMYSHLENIYA LLM\n")
                        f.write(f"{THIN_LINE}\n")
                        f.write(f"{content}\n")

                elif event_type == "llm_final":
                    content = data.get("content", "")
                    if content:
                        f.write(f"\n{THIN_LINE}\n")
                        f.write(f"[{timestamp}] OTVET LLM\n")
                        f.write(f"{THIN_LINE}\n")
                        f.write(f"{content}\n")

                elif event_type == "llm_token":
                    # Токены пропускаем - финальный ответ записывается в llm_final
                    pass

                elif event_type == "error":
                    message = data.get("message", "")
                    f.write(f"\n{THIN_LINE}\n")
                    f.write(f"[{timestamp}] OSHIBKA\n")
                    f.write(f"{THIN_LINE}\n")
                    f.write(f"{message}\n")

                elif event_type == "completed":
                    f.write(f"\n{THICK_LINE}\n")
                    f.write(f"[{timestamp}] ZAVERSHENO\n")
                    f.write(f"{THICK_LINE}\n\n")

                elif event_type == "queue_position":
                    position = data.get("position", 0)
                    f.write(f"\n[{timestamp}] Poziciya v ocheredi: {position}\n")

                elif event_type == "processing_started":
                    f.write(f"\n[{timestamp}] Obrabotka nachalas\n")

                else:
                    # Прочие события - записываем как JSON
                    f.write(f"\n[{timestamp}] [{event_type}]\n")
                    f.write(json.dumps(data, ensure_ascii=False, indent=4))
                    f.write("\n")

        except Exception as e:
            logger.error(f"Error logging SSE event: {e}")
    
    def save_chat_image(
        self,
        chat_id: str,
        image_data: bytes,
        image_type: str,
        filename: Optional[str] = None
    ) -> Optional[str]:
        """
        Сохранить изображение в папку crops чата.
        
        Args:
            chat_id: ID чата
            image_data: Байты изображения
            image_type: Тип изображения (для имени файла)
            filename: Имя файла (опционально, генерируется автоматически)
        
        Returns:
            Путь к сохранённому файлу или None при ошибке
        """
        try:
            crops_dir = self.get_crops_dir(chat_id)
            
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                # Определяем расширение по типу
                ext = ".png"
                if image_type:
                    if "jpeg" in image_type.lower() or "jpg" in image_type.lower():
                        ext = ".jpg"
                    elif "png" in image_type.lower():
                        ext = ".png"
                    elif "gif" in image_type.lower():
                        ext = ".gif"
                    elif "webp" in image_type.lower():
                        ext = ".webp"
                filename = f"{image_type}_{timestamp}{ext}"
            
            file_path = crops_dir / filename
            
            with open(file_path, "wb") as f:
                f.write(image_data)
            
            logger.info(f"Saved image: {file_path}")
            return str(file_path)
            
        except Exception as e:
            logger.error(f"Error saving chat image: {e}")
            return None


# Глобальный экземпляр менеджера конфигурации
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_dir: Optional[Path] = None) -> ConfigManager:
    """
    Получить глобальный экземпляр менеджера конфигурации.
    
    Args:
        config_dir: Путь к директории конфигурации
    
    Returns:
        ConfigManager
    """
    global _config_manager
    
    if _config_manager is None or config_dir is not None:
        _config_manager = ConfigManager(config_dir)
    
    return _config_manager


