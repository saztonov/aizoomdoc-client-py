"""
Управление конфигурацией и хранением токенов.

Хранит данные в файле в домашней директории пользователя.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from aizoomdoc_client.models import ClientConfig, TokenData


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
                server_url="http://localhost:8000",
                token_data=None,
                active_chat_id=None
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
                server_url="http://localhost:8000",
                token_data=None,
                active_chat_id=None
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
            "active_chat_id": str(self._config.active_chat_id) if self._config.active_chat_id else None
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
            active_chat_id=None
        )
        self.save()


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

