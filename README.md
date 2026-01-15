# AIZoomDoc Python Client

Локальный Python-клиент для работы с [AIZoomDoc Server](../aizoomdoc-server).

## Установка

```bash
# Клонирование репозитория
cd aizoomdoc-client-py

# Установка зависимостей
pip install -e .

# Или через requirements.txt
pip install -r requirements.txt
```

## Быстрый старт

### CLI интерфейс

```bash
# Авторизация
aizoomdoc login --token YOUR_STATIC_TOKEN

# Проверка соединения
aizoomdoc health

# Информация о пользователе
aizoomdoc me

# Создание чата
aizoomdoc chat new "Анализ документации"

# Отправка сообщения (со стримингом ответа)
aizoomdoc chat send "Какое оборудование установлено в системе В2?"

# История чата
aizoomdoc chat history

# Смена режима модели
aizoomdoc settings set-model complex

# Выбор роли
aizoomdoc settings set-role "Инженер"

# Загрузка файла
aizoomdoc file upload document.pdf

# Выход
aizoomdoc logout
```

### Использование как библиотека

```python
from aizoomdoc_client import AIZoomDocClient

# Создание клиента
client = AIZoomDocClient(
    server_url="http://localhost:8000",
    static_token="your-static-token"
)

# Авторизация (автоматически при первом запросе)
client.authenticate()

# Создание чата
chat = client.create_chat(title="Мой анализ")

# Отправка сообщения со стримингом
for event in client.send_message(chat.id, "Какое оборудование?"):
    if event.event == "llm_token":
        print(event.data["token"], end="", flush=True)
    elif event.event == "phase_started":
        print(f"\n[{event.data['phase']}] {event.data['description']}")

# Получение настроек
me = client.get_me()
print(f"Режим: {me.settings.model_profile}")

# Смена режима
client.update_settings(model_profile="complex")

# Загрузка файла
file_info = client.upload_file("document.pdf")

# Отправка с вложением
for event in client.send_message(chat.id, "Проанализируй", attached_file_ids=[file_info.id]):
    ...
```

## Команды CLI

### Аутентификация

| Команда | Описание |
|---------|----------|
| `aizoomdoc login --token TOKEN` | Авторизация по статичному токену |
| `aizoomdoc logout` | Выход из системы |
| `aizoomdoc me` | Информация о текущем пользователе |
| `aizoomdoc health` | Проверка доступности сервера |

### Настройки

| Команда | Описание |
|---------|----------|
| `aizoomdoc settings set-model simple\|complex` | Установить режим модели |
| `aizoomdoc settings set-role ROLE` | Установить роль (имя или ID) |
| `aizoomdoc settings set-role none` | Сбросить роль |
| `aizoomdoc settings list-roles` | Показать доступные роли |

### Чаты

| Команда | Описание |
|---------|----------|
| `aizoomdoc chat new "Название"` | Создать новый чат |
| `aizoomdoc chat list` | Показать список чатов |
| `aizoomdoc chat use CHAT_ID` | Выбрать активный чат |
| `aizoomdoc chat send "Сообщение"` | Отправить сообщение |
| `aizoomdoc chat history` | Показать историю |

### Файлы

| Команда | Описание |
|---------|----------|
| `aizoomdoc file upload PATH` | Загрузить файл |

### Проекты (только чтение)

| Команда | Описание |
|---------|----------|
| `aizoomdoc projects tree` | Показать дерево проектов |
| `aizoomdoc projects search "запрос"` | Поиск документов |

## Конфигурация

Клиент хранит конфигурацию в `~/.aizoomdoc/config.json`:

```json
{
  "server_url": "http://localhost:8000",
  "token_data": {
    "access_token": "...",
    "expires_at": "2026-01-15T12:00:00",
    "user_id": "...",
    "username": "user"
  },
  "active_chat_id": "..."
}
```

### Переменные окружения

| Переменная | Описание |
|------------|----------|
| `AIZOOMDOC_SERVER` | URL сервера |
| `AIZOOMDOC_TOKEN` | Статичный токен (для автоматической авторизации) |

## Обработка ошибок

```python
from aizoomdoc_client.exceptions import (
    AuthenticationError,
    TokenExpiredError,
    APIError,
    NotFoundError,
    ServerError
)

try:
    client.send_message(chat_id, message)
except TokenExpiredError:
    # Токен истёк, нужна переавторизация
    client.authenticate()
except AuthenticationError:
    # Неверный токен
    print("Проверьте токен")
except NotFoundError:
    # Ресурс не найден
    print("Чат не найден")
except ServerError as e:
    # Ошибка сервера
    print(f"Ошибка сервера: {e.message}")
except APIError as e:
    # Другие ошибки API
    print(f"Ошибка: {e}")
```

## События стриминга

При отправке сообщения клиент получает поток событий:

| Событие | Описание |
|---------|----------|
| `phase_started` | Начало фазы обработки (search, processing, llm) |
| `phase_progress` | Прогресс текущей фазы |
| `llm_token` | Токен от LLM (для стриминга ответа) |
| `llm_final` | Финальный ответ LLM |
| `tool_call` | Вызов инструмента (request_images, zoom) |
| `error` | Ошибка обработки |
| `completed` | Обработка завершена |

## Разработка

```bash
# Установка dev-зависимостей
pip install -e ".[dev]"

# Запуск тестов
pytest

# Проверка типов
mypy src/
```

## Архитектура

```
src/aizoomdoc_client/
├── __init__.py          # Публичный API
├── client.py            # Основной клиент AIZoomDocClient
├── http_client.py       # HTTP клиент с авто-refresh
├── config.py            # Управление конфигурацией и токенами
├── models.py            # Pydantic модели
├── exceptions.py        # Исключения
└── cli.py               # CLI интерфейс (click + rich)
```

## Зависимости

- **httpx** - HTTP клиент с поддержкой async
- **httpx-sse** - SSE стриминг
- **click** - CLI фреймворк
- **rich** - Красивый вывод в консоль
- **pydantic** - Валидация данных
- **websockets** - WebSocket поддержка

## Лицензия

MIT

