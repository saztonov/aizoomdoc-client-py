"""
CLI интерфейс для AIZoomDoc Client.

Использование:
    aizoomdoc login --token YOUR_TOKEN
    aizoomdoc me
    aizoomdoc chat new "Мой чат"
    aizoomdoc chat send "Вопрос"
    aizoomdoc settings set-model complex
"""

import sys
import os
from pathlib import Path
from typing import Optional
from uuid import UUID

# Windows кодировка
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text

from aizoomdoc_client.client import AIZoomDocClient
from aizoomdoc_client.config import get_config_manager
from aizoomdoc_client.exceptions import (
    AIZoomDocError,
    AuthenticationError,
    TokenExpiredError,
)

console = Console()

# Глобальные опции
pass_client = click.make_pass_decorator(AIZoomDocClient, ensure=True)


def get_client(server_url: Optional[str] = None) -> AIZoomDocClient:
    """Получить клиент с текущей конфигурацией."""
    config = get_config_manager()
    url = server_url or config.get_config().server_url
    return AIZoomDocClient(server_url=url)


def error(message: str) -> None:
    """Вывести ошибку."""
    console.print(f"[red]✗[/red] {message}")


def success(message: str) -> None:
    """Вывести успех."""
    console.print(f"[green]✓[/green] {message}")


def info(message: str) -> None:
    """Вывести информацию."""
    console.print(f"[blue]ℹ[/blue] {message}")


@click.group()
@click.option(
    "--server", "-s",
    envvar="AIZOOMDOC_SERVER",
    help="URL сервера (по умолчанию: http://localhost:8000)"
)
@click.pass_context
def main(ctx, server: Optional[str]):
    """AIZoomDoc CLI - клиент для работы с сервером анализа документации."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


# ===== AUTH COMMANDS =====

@main.command()
@click.option("--token", "-t", prompt=True, hide_input=True, help="Статичный токен")
@click.option("--server", "-s", help="URL сервера")
@click.pass_context
def login(ctx, token: str, server: Optional[str]):
    """Авторизоваться по статичному токену."""
    server_url = server or ctx.obj.get("server")
    
    try:
        client = AIZoomDocClient(server_url=server_url, static_token=token)
        result = client.authenticate()
        
        success(f"Авторизован как [bold]{result.user.username}[/bold]")
        info(f"Токен истекает через {result.expires_in // 60} минут")
        
    except AuthenticationError as e:
        error(f"Ошибка авторизации: {e.message}")
        sys.exit(1)
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@main.command()
@click.pass_context
def logout(ctx):
    """Выйти из системы."""
    client = get_client(ctx.obj.get("server"))
    client.logout()
    success("Вы вышли из системы")


@main.command()
@click.pass_context
def me(ctx):
    """Показать информацию о текущем пользователе."""
    try:
        client = get_client(ctx.obj.get("server"))
        user_info = client.get_me()
        
        table = Table(title="Пользователь", show_header=False)
        table.add_column("Параметр", style="cyan")
        table.add_column("Значение")
        
        table.add_row("ID", str(user_info.user.id))
        table.add_row("Имя", user_info.user.username)
        table.add_row("Статус", user_info.user.status)
        table.add_row("Режим модели", user_info.settings.model_profile)
        table.add_row(
            "Роль",
            str(user_info.settings.selected_role_prompt_id) or "не выбрана"
        )
        table.add_row(
            "Gemini API Key",
            "✓ настроен" if user_info.gemini_api_key_configured else "✗ не настроен"
        )
        
        console.print(table)
        
    except TokenExpiredError:
        error("Токен истёк. Выполните: aizoomdoc login")
        sys.exit(1)
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


# ===== SETTINGS COMMANDS =====

@main.group()
def settings():
    """Управление настройками пользователя."""
    pass


@settings.command("set-model")
@click.argument("profile", type=click.Choice(["simple", "complex"]))
@click.pass_context
def set_model(ctx, profile: str):
    """Установить режим модели (simple/complex)."""
    try:
        client = get_client(ctx.obj.get("server"))
        result = client.update_settings(model_profile=profile)
        success(f"Режим модели изменён на: [bold]{result.model_profile}[/bold]")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@settings.command("set-role")
@click.argument("role")
@click.pass_context
def set_role(ctx, role: str):
    """Установить роль (имя или 'none' для сброса)."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        if role.lower() == "none":
            # Сброс роли
            client.update_settings(selected_role_prompt_id=None)
            success("Роль сброшена")
        else:
            # Поиск роли по имени
            roles = client.get_available_roles()
            matched = None
            for r in roles:
                if r.name.lower() == role.lower() or str(r.id) == role:
                    matched = r
                    break
            
            if not matched:
                available = ", ".join(r.name for r in roles)
                error(f"Роль '{role}' не найдена. Доступные: {available}")
                sys.exit(1)
            
            client.update_settings(selected_role_prompt_id=matched.id)
            success(f"Роль установлена: [bold]{matched.name}[/bold]")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@settings.command("list-roles")
@click.pass_context
def list_roles(ctx):
    """Показать доступные роли."""
    try:
        client = get_client(ctx.obj.get("server"))
        roles = client.get_available_roles()
        
        if not roles:
            info("Нет доступных ролей")
            return
        
        table = Table(title="Доступные роли")
        table.add_column("Название", style="cyan")
        table.add_column("Описание")
        table.add_column("ID", style="dim")
        
        for role in roles:
            table.add_row(
                role.name,
                role.description or "-",
                str(role.id)[:8] + "..."
            )
        
        console.print(table)
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


# ===== CHAT COMMANDS =====

@main.group()
def chat():
    """Работа с чатами."""
    pass


@chat.command("new")
@click.argument("title", required=False)
@click.option("--description", "-d", help="Описание чата")
@click.pass_context
def chat_new(ctx, title: Optional[str], description: Optional[str]):
    """Создать новый чат."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        chat = client.create_chat(
            title=title or "Новый чат",
            description=description
        )
        
        success(f"Чат создан: [bold]{chat.title}[/bold]")
        info(f"ID: {chat.id}")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@chat.command("use")
@click.argument("chat_id")
@click.pass_context
def chat_use(ctx, chat_id: str):
    """Выбрать активный чат."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        chat = client.use_chat(UUID(chat_id))
        success(f"Активный чат: [bold]{chat.title}[/bold]")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@chat.command("list")
@click.option("--limit", "-n", default=10, help="Количество чатов")
@click.pass_context
def chat_list(ctx, limit: int):
    """Показать список чатов."""
    try:
        client = get_client(ctx.obj.get("server"))
        chats = client.list_chats(limit=limit)
        
        if not chats:
            info("Нет чатов")
            return
        
        active_id = client.get_active_chat_id()
        
        table = Table(title="Чаты")
        table.add_column("", width=2)
        table.add_column("Название", style="cyan")
        table.add_column("Создан")
        table.add_column("ID", style="dim")
        
        for c in chats:
            marker = "→" if c.id == active_id else ""
            table.add_row(
                marker,
                c.title,
                c.created_at.strftime("%Y-%m-%d %H:%M"),
                str(c.id)[:8] + "..."
            )
        
        console.print(table)
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@chat.command("send")
@click.argument("message")
@click.option("--chat-id", "-c", help="ID чата (если не указан - активный)")
@click.option("--no-stream", is_flag=True, help="Отключить стриминг")
@click.pass_context
def chat_send(ctx, message: str, chat_id: Optional[str], no_stream: bool):
    """Отправить сообщение в чат."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        # Определяем ID чата
        if chat_id:
            target_chat_id = UUID(chat_id)
        else:
            target_chat_id = client.get_active_chat_id()
            if not target_chat_id:
                error("Нет активного чата. Создайте: aizoomdoc chat new")
                sys.exit(1)
        
        console.print(f"\n[dim]Вы:[/dim] {message}\n")
        
        if no_stream:
            # Синхронный режим
            with console.status("Ожидание ответа..."):
                response = client.send_message_sync(target_chat_id, message)
            
            console.print(Panel(
                Markdown(response.content),
                title="Ассистент",
                border_style="green"
            ))
        else:
            # Стриминг
            response_text = ""
            current_phase = ""
            
            console.print("[dim]Ассистент:[/dim]")
            
            for event in client.send_message(target_chat_id, message):
                if event.event == "phase_started":
                    phase = event.data.get("phase", "")
                    desc = event.data.get("description", "")
                    if phase != current_phase:
                        current_phase = phase
                        console.print(f"\n[dim cyan]→ {desc}[/dim cyan]")
                
                elif event.event == "phase_progress":
                    pass  # Можно добавить progress bar
                
                elif event.event == "llm_token":
                    token = event.data.get("token", "")
                    response_text += token
                    console.print(token, end="")
                
                elif event.event == "llm_final":
                    response_text = event.data.get("content", response_text)
                
                elif event.event == "tool_call":
                    tool = event.data.get("tool", "")
                    reason = event.data.get("reason", "")
                    console.print(f"\n[dim yellow]🔧 {tool}: {reason}[/dim yellow]")
                
                elif event.event == "error":
                    err_msg = event.data.get("message", "Unknown error")
                    console.print(f"\n[red]Ошибка: {err_msg}[/red]")
                
                elif event.event == "completed":
                    pass
            
            console.print("\n")  # Завершающий перевод строки
        
    except TokenExpiredError:
        error("Токен истёк. Выполните: aizoomdoc login")
        sys.exit(1)
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@chat.command("history")
@click.option("--chat-id", "-c", help="ID чата")
@click.option("--tail", "-n", default=10, help="Количество сообщений")
@click.pass_context
def chat_history(ctx, chat_id: Optional[str], tail: int):
    """Показать историю сообщений."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        # Определяем ID чата
        if chat_id:
            target_chat_id = UUID(chat_id)
        else:
            target_chat_id = client.get_active_chat_id()
            if not target_chat_id:
                error("Нет активного чата")
                sys.exit(1)
        
        history = client.get_chat_history(target_chat_id)
        
        console.print(Panel(f"[bold]{history.chat.title}[/bold]", border_style="blue"))
        
        messages = history.messages[-tail:] if tail else history.messages
        
        for msg in messages:
            if msg.role == "user":
                console.print(f"\n[bold blue]Вы[/bold blue] [dim]{msg.created_at.strftime('%H:%M')}[/dim]")
                console.print(msg.content)
            elif msg.role == "assistant":
                console.print(f"\n[bold green]Ассистент[/bold green] [dim]{msg.created_at.strftime('%H:%M')}[/dim]")
                console.print(Markdown(msg.content))
            else:
                console.print(f"\n[dim]{msg.role}:[/dim] {msg.content}")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


# ===== FILE COMMANDS =====

@main.group()
def file():
    """Работа с файлами."""
    pass


@file.command("upload")
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def file_upload(ctx, file_path: str):
    """Загрузить файл на сервер."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        path = Path(file_path)
        with console.status(f"Загрузка {path.name}..."):
            result = client.upload_file(path)
        
        success(f"Файл загружен: [bold]{result.filename}[/bold]")
        info(f"ID: {result.id}")
        info(f"Размер: {result.size_bytes:,} байт")
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


# ===== PROJECTS COMMANDS =====

@main.group()
def projects():
    """Работа с деревом проектов (только чтение)."""
    pass


@projects.command("tree")
@click.option("--client-id", "-c", help="ID клиента (организации)")
@click.option("--parent-id", "-p", help="ID родительского узла")
@click.pass_context
def projects_tree(ctx, client_id: Optional[str], parent_id: Optional[str]):
    """Показать дерево проектов."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        parent_uuid = UUID(parent_id) if parent_id else None
        nodes = client.get_projects_tree(client_id=client_id, parent_id=parent_uuid)
        
        if not nodes:
            info("Нет узлов")
            return
        
        table = Table(title="Дерево проектов")
        table.add_column("Тип", style="cyan", width=10)
        table.add_column("Название")
        table.add_column("Код", style="dim")
        table.add_column("ID", style="dim")
        
        for node in nodes:
            table.add_row(
                node.node_type,
                node.name,
                node.code or "-",
                str(node.id)[:8] + "..."
            )
        
        console.print(table)
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


@projects.command("search")
@click.argument("query")
@click.option("--client-id", "-c", help="ID клиента")
@click.option("--limit", "-n", default=10, help="Количество результатов")
@click.pass_context
def projects_search(ctx, query: str, client_id: Optional[str], limit: int):
    """Поиск документов."""
    try:
        client = get_client(ctx.obj.get("server"))
        
        results = client.search_documents(query, client_id=client_id, limit=limit)
        
        if not results:
            info("Ничего не найдено")
            return
        
        table = Table(title=f"Результаты поиска: {query}")
        table.add_column("Название", style="cyan")
        table.add_column("Тип")
        table.add_column("ID", style="dim")
        
        for node in results:
            table.add_row(
                node.name,
                node.node_type,
                str(node.id)[:8] + "..."
            )
        
        console.print(table)
        
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


# ===== HEALTH CHECK =====

@main.command()
@click.pass_context
def health(ctx):
    """Проверить состояние сервера."""
    import httpx
    
    try:
        config = get_config_manager()
        url = ctx.obj.get("server") or config.get_config().server_url
        
        with httpx.Client() as client:
            response = client.get(f"{url}/health")
        
        if response.is_success:
            data = response.json()
            success(f"Сервер доступен: {data.get('status', 'ok')}")
            info(f"Версия: {data.get('version', 'unknown')}")
        else:
            error(f"Сервер вернул ошибку: {response.status_code}")
            
    except httpx.ConnectError:
        error(f"Не удалось подключиться к серверу")
        sys.exit(1)
    except Exception as e:
        error(f"Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

