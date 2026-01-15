"""
Скрипт для тестирования подключения к серверу.

Запуск:
    python test_connection.py
"""

import sys
import os

# Фикс для Windows кодировки
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

sys.path.insert(0, "src")

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Force terminal для Windows
console = Console(force_terminal=True, legacy_windows=False)

SERVER_URL = "http://localhost:8000"


def test_health():
    """Проверка доступности сервера."""
    console.print("\n[bold]1. Проверка доступности сервера[/bold]")
    
    try:
        response = httpx.get(f"{SERVER_URL}/health", timeout=10.0)
        
        if response.is_success:
            data = response.json()
            console.print(f"  [green][OK][/green] Сервер доступен")
            console.print(f"    Статус: {data.get('status')}")
            console.print(f"    Версия: {data.get('version')}")
            console.print(f"    Сервис: {data.get('service')}")
            return True
        else:
            console.print(f"  [red][FAIL][/red] Сервер вернул ошибку: {response.status_code}")
            return False
            
    except httpx.ConnectError:
        console.print(f"  [red][FAIL][/red] Не удалось подключиться к {SERVER_URL}")
        console.print("    Убедитесь, что сервер запущен (docker-compose up)")
        return False
    except Exception as e:
        console.print(f"  [red][FAIL][/red] Ошибка: {e}")
        return False


def test_api_docs():
    """Проверка документации API."""
    console.print("\n[bold]2. Проверка документации API[/bold]")
    
    try:
        response = httpx.get(f"{SERVER_URL}/docs", timeout=10.0, follow_redirects=True)
        
        if response.is_success:
            console.print(f"  [green][OK][/green] Swagger UI доступен: {SERVER_URL}/docs")
            return True
        else:
            console.print(f"  [yellow][WARN][/yellow] Docs недоступны: {response.status_code}")
            return False
            
    except Exception as e:
        console.print(f"  [yellow][WARN][/yellow] Ошибка: {e}")
        return False


def test_auth_endpoint():
    """Проверка эндпоинта авторизации."""
    console.print("\n[bold]3. Проверка эндпоинта авторизации[/bold]")
    
    try:
        # Тестируем с неверным токеном (ожидаем 401)
        response = httpx.post(
            f"{SERVER_URL}/auth/exchange",
            json={"static_token": "invalid-test-token"},
            timeout=10.0
        )
        
        if response.status_code == 401:
            console.print(f"  [green][OK][/green] Эндпоинт /auth/exchange работает")
            console.print(f"    Ответ на неверный токен: 401 Unauthorized (ожидаемо)")
            return True
        elif response.is_success:
            console.print(f"  [green][OK][/green] Авторизация успешна (токен валиден)")
            return True
        else:
            console.print(f"  [yellow][WARN][/yellow] Неожиданный ответ: {response.status_code}")
            console.print(f"    {response.text}")
            return False
            
    except Exception as e:
        console.print(f"  [red][FAIL][/red] Ошибка: {e}")
        return False


def test_endpoints():
    """Проверка основных эндпоинтов (без авторизации)."""
    console.print("\n[bold]4. Проверка основных эндпоинтов[/bold]")
    
    endpoints = [
        ("GET", "/", "Корневой эндпоинт"),
        ("GET", "/health", "Health check"),
    ]
    
    all_ok = True
    
    for method, path, description in endpoints:
        try:
            if method == "GET":
                response = httpx.get(f"{SERVER_URL}{path}", timeout=10.0)
            else:
                response = httpx.request(method, f"{SERVER_URL}{path}", timeout=10.0)
            
            status = "[green][OK][/green]" if response.is_success else "[yellow][WARN][/yellow]"
            console.print(f"  {status} {method} {path} - {response.status_code} ({description})")
            
        except Exception as e:
            console.print(f"  [red][FAIL][/red] {method} {path} - Ошибка: {e}")
            all_ok = False
    
    return all_ok


def show_client_usage():
    """Показать примеры использования клиента."""
    console.print("\n[bold]Использование клиента:[/bold]\n")
    
    usage = """
# Установка зависимостей
pip install -r requirements.txt

# Или установка пакета
pip install -e .

# CLI: Авторизация
aizoomdoc login --token YOUR_STATIC_TOKEN

# CLI: Проверка
aizoomdoc health
aizoomdoc me

# CLI: Работа с чатами
aizoomdoc chat new "Тестовый чат"
aizoomdoc chat send "Какое оборудование?"

# Python API:
from aizoomdoc_client import AIZoomDocClient

client = AIZoomDocClient(
    server_url="http://localhost:8000",
    static_token="your-token"
)
client.authenticate()
"""
    
    console.print(Panel(usage.strip(), title="Примеры", border_style="blue"))


def main():
    console.print(Panel.fit(
        "[bold blue]AIZoomDoc Client - Тест подключения[/bold blue]",
        border_style="blue"
    ))
    
    console.print(f"\nСервер: {SERVER_URL}\n")
    
    results = []
    
    results.append(("Health Check", test_health()))
    results.append(("API Docs", test_api_docs()))
    results.append(("Auth Endpoint", test_auth_endpoint()))
    results.append(("Endpoints", test_endpoints()))
    
    # Итоги
    console.print("\n" + "=" * 50)
    console.print("[bold]Результаты:[/bold]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("Тест")
    table.add_column("Результат")
    
    all_passed = True
    for name, result in results:
        status = "[green]PASS[/green]" if result else "[red]FAIL[/red]"
        table.add_row(name, status)
        if not result:
            all_passed = False
    
    console.print(table)
    
    if all_passed:
        console.print("\n[bold green]Все тесты пройдены![/bold green]")
        show_client_usage()
    else:
        console.print("\n[bold yellow]Некоторые тесты не прошли[/bold yellow]")
        console.print("Проверьте, что сервер запущен: docker-compose up")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
