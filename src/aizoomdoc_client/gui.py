# -*- coding: utf-8 -*-
"""
AIZoomDoc Client GUI (PyQt6).
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

# Fix encoding for Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox, QSplitter,
    QListWidget, QListWidgetItem, QFrame, QScrollArea, QProgressBar,
    QMenuBar, QMenu, QDialog, QDialogButtonBox, QMessageBox,
    QGroupBox, QSizePolicy, QTabWidget, QTextBrowser, QStackedWidget,
    QStatusBar, QToolBar, QTreeWidget, QTreeWidgetItem, QButtonGroup
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QUrl, QByteArray
from PyQt6.QtGui import QFont, QAction, QTextCursor, QIcon, QColor, QPixmap, QImage
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from aizoomdoc_client.client import AIZoomDocClient
from aizoomdoc_client.config import get_config_manager
from aizoomdoc_client.models import (
    ChatResponse, MessageResponse, StreamEvent, 
    UserMeResponse, PromptUserRole
)
from aizoomdoc_client.exceptions import (
    AIZoomDocError, AuthenticationError, TokenExpiredError
)

logger = logging.getLogger(__name__)


def fix_mojibake(text: str) -> str:
    """Fix mojibake (double-encoded UTF-8 text)."""
    if not text:
        return text
    
    try:
        # UTF-8 bytes were interpreted as CP1251 -> encode back to CP1251, decode as UTF-8
        fixed = text.encode('cp1251').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


class StreamWorker(QThread):
    """Worker for LLM response streaming."""
    
    token_received = pyqtSignal(str)
    phase_started = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)
    completed = pyqtSignal()
    
    def __init__(
        self,
        client: AIZoomDocClient,
        chat_id: str,
        message: str,
        document_ids: Optional[List[str]] = None,
        client_id: Optional[str] = None
    ):
        super().__init__()
        self.client = client
        self.chat_id = chat_id
        self.message = message
        self.document_ids = document_ids or []
        self.client_id = client_id
        self._stop_requested = False
    
    def run(self):
        try:
            from uuid import UUID
            chat_uuid = UUID(self.chat_id)
            
            from uuid import UUID
            doc_ids = [UUID(did) for did in self.document_ids] if self.document_ids else None
            for event in self.client.send_message(
                chat_uuid,
                self.message,
                attached_document_ids=doc_ids,
                client_id=self.client_id
            ):
                if self._stop_requested:
                    break
                
                if event.event == "llm_token":
                    token = event.data.get("token", "")
                    self.token_received.emit(token)
                elif event.event == "phase_started":
                    phase = event.data.get("phase", "")
                    desc = event.data.get("description", "")
                    self.phase_started.emit(phase, desc)
                elif event.event == "error":
                    msg = event.data.get("message", "Unknown error")
                    self.error_occurred.emit(msg)
            
            self.completed.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
    
    def stop(self):
        self._stop_requested = True


class LoginDialog(QDialog):
    """Login dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Авторизация - AIZoomDoc")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        # Server
        server_group = QGroupBox("Сервер")
        server_layout = QVBoxLayout(server_group)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("http://localhost:8000")
        config = get_config_manager().get_config()
        self.server_edit.setText(config.server_url)
        server_layout.addWidget(self.server_edit)
        layout.addWidget(server_group)
        
        # Token
        token_group = QGroupBox("Статичный токен")
        token_layout = QHBoxLayout(token_group)
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Введите ваш статичный токен")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token_layout.addWidget(self.token_edit)
        
        self.show_token_btn = QPushButton("👁")
        self.show_token_btn.setFixedWidth(40)
        self.show_token_btn.setCheckable(True)
        self.show_token_btn.clicked.connect(self._toggle_visibility)
        token_layout.addWidget(self.show_token_btn)
        layout.addWidget(token_group)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red;")
        layout.addWidget(self.status_label)
    
    def _toggle_visibility(self):
        if self.show_token_btn.isChecked():
            self.token_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
    
    def get_credentials(self):
        return self.server_edit.text().strip(), self.token_edit.text().strip()
    
    def set_error(self, message: str):
        self.status_label.setText(message)


class SettingsDialog(QDialog):
    """Settings dialog."""
    
    def __init__(self, client: AIZoomDocClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        # Model mode
        model_group = QGroupBox("Режим модели")
        model_layout = QVBoxLayout(model_group)
        self.model_combo = QComboBox()
        self.model_combo.addItem("Простой (Flash)", "simple")
        self.model_combo.addItem("Сложный (Flash + Pro)", "complex")
        model_layout.addWidget(self.model_combo)
        layout.addWidget(model_group)
        
        # Role
        role_group = QGroupBox("Роль")
        role_layout = QVBoxLayout(role_group)
        self.role_combo = QComboBox()
        self.role_combo.addItem("Без роли", None)
        role_layout.addWidget(self.role_combo)
        layout.addWidget(role_group)
        
        self._load_settings()
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def _load_settings(self):
        try:
            user_info = self.client.get_me()
            idx = self.model_combo.findData(user_info.settings.model_profile)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            
            roles = self.client.get_available_roles()
            for role in roles:
                name = fix_mojibake(role.name)
                self.role_combo.addItem(name, role.id)
            
            if user_info.settings.selected_role_prompt_id:
                idx = self.role_combo.findData(user_info.settings.selected_role_prompt_id)
                if idx >= 0:
                    self.role_combo.setCurrentIndex(idx)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def _save_and_accept(self):
        try:
            self.client.update_settings(
                model_profile=self.model_combo.currentData(),
                selected_role_prompt_id=self.role_combo.currentData()
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")


class ChatWidget(QWidget):
    """Chat widget with messages."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client: Optional[AIZoomDocClient] = None
        self.current_chat_id: Optional[str] = None
        self.worker: Optional[StreamWorker] = None
        self.attachments_provider = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Messages area
        self.messages_area = QTextBrowser()
        self.messages_area.setOpenExternalLinks(True)
        self.messages_area.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self.messages_area, 1)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.status_label)
        
        # Input area
        input_layout = QHBoxLayout()
        self.input_edit = QTextEdit()
        self.input_edit.setMaximumHeight(100)
        self.input_edit.setPlaceholderText("Введите сообщение...")
        self.input_edit.setFont(QFont("Segoe UI", 11))
        input_layout.addWidget(self.input_edit, 1)
        
        self.send_btn = QPushButton("Отправить")
        self.send_btn.setMinimumHeight(50)
        self.send_btn.setMinimumWidth(100)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)
        
        layout.addLayout(input_layout)
    
    def set_chat(self, chat_id: str):
        self.current_chat_id = chat_id
        self._load_history()
    
    def _load_history(self):
        if not self.current_chat_id or not self.client:
            return
        
        try:
            from uuid import UUID
            history = self.client.get_chat_history(UUID(self.current_chat_id))
            
            self.messages_area.clear()
            for msg in history.messages:
                content = fix_mojibake(msg.content)
                images = getattr(msg, 'images', [])
                self._append_message(msg.role, content, images)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
    
    def _append_message(self, role: str, content: str, images: list = None):
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if role == "user":
            html = f'<p style="color: #0066cc; margin: 10px 0;"><b>Вы:</b></p>'
            html += f'<p style="margin: 5px 0 15px 20px; white-space: pre-wrap;">{content}</p>'
        elif role == "assistant":
            html = f'<p style="color: #009933; margin: 10px 0;"><b>Ассистент:</b></p>'
            formatted = content.replace('\n', '<br>')
            html += f'<p style="margin: 5px 0 15px 20px;">{formatted}</p>'
        else:
            html = f'<p style="color: #666;">{content}</p>'
        
        # Добавляем изображения
        if images:
            html += '<div style="margin: 10px 20px;">'
            for img in images:
                url = getattr(img, 'url', None) or (img.get('url') if isinstance(img, dict) else None)
                if url:
                    img_type = getattr(img, 'image_type', '') or (img.get('image_type', '') if isinstance(img, dict) else '')
                    # Загружаем изображение и конвертируем в base64
                    try:
                        import httpx
                        import base64
                        response = httpx.get(url, timeout=10.0)
                        if response.status_code == 200:
                            content_type = response.headers.get('content-type', '')
                            if content_type.startswith('image/'):
                                img_data = base64.b64encode(response.content).decode('utf-8')
                                data_url = f"data:{content_type};base64,{img_data}"
                                html += f'<p><a href="{url}"><img src="{data_url}" width="400" style="max-width: 100%; border: 1px solid #ccc; margin: 5px 0;"/></a>'
                                html += f'<br/><small style="color: #666;">{img_type}</small></p>'
                            else:
                                html += f'<p><a href="{url}">[Файл: {img_type}]</a></p>'
                        else:
                            html += f'<p><a href="{url}">[Файл: {img_type}]</a></p>'
                    except Exception as e:
                        logger.error(f"Error loading image: {e}")
                        html += f'<p><a href="{url}">[Файл: {img_type}]</a></p>'
            html += '</div>'
        
        cursor.insertHtml(html)
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()
    
    def _send_message(self):
        if not self.current_chat_id:
            QMessageBox.warning(self, "Ошибка", "Сначала выберите или создайте чат")
            return
        
        message = self.input_edit.toPlainText().strip()
        if not message:
            return
        
        self.input_edit.clear()
        self._append_message("user", message)
        self._start_streaming(message)
    
    def _start_streaming(self, message: str):
        self.send_btn.setEnabled(False)
        self.status_label.setText("Обработка...")
        
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml('<p style="color: #009933; margin: 10px 0;"><b>Ассистент:</b></p><p style="margin: 5px 0 15px 20px;">')
        self.messages_area.setTextCursor(cursor)
        
        document_ids = []
        client_id = None
        if callable(self.attachments_provider):
            ctx = self.attachments_provider() or {}
            document_ids = ctx.get("document_ids", [])
            client_id = ctx.get("client_id")

        if not client_id:
            QMessageBox.warning(self, "Ошибка", "Не указан Client ID (вкладка Дерево)")
            self.send_btn.setEnabled(True)
            self.status_label.setText("")
            return

        self.worker = StreamWorker(
            self.client,
            self.current_chat_id,
            message,
            document_ids=document_ids,
            client_id=client_id
        )
        self.worker.token_received.connect(self._on_token)
        self.worker.phase_started.connect(self._on_phase)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.completed.connect(self._on_completed)
        self.worker.start()
    
    def _on_token(self, token: str):
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()
    
    def _on_phase(self, phase: str, desc: str):
        self.status_label.setText(f"[{phase}] {desc}")
    
    def _on_error(self, error: str):
        self.status_label.setText(f"Ошибка: {error}")
        self.send_btn.setEnabled(True)
    
    def _on_completed(self):
        self.status_label.setText("")
        self.send_btn.setEnabled(True)
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml('</p>')


class LeftPanel(QWidget):
    """Left panel with Chats/Tree tabs."""
    
    chat_selected = pyqtSignal(str)  # chat_id
    new_chat_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client: Optional[AIZoomDocClient] = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Tab buttons
        tabs_layout = QHBoxLayout()
        tabs_layout.setContentsMargins(5, 5, 5, 0)
        
        self.btn_chats = QPushButton("Чаты")
        self.btn_chats.setCheckable(True)
        self.btn_chats.setChecked(True)
        self.btn_chats.setFixedHeight(32)
        self.btn_chats.clicked.connect(lambda: self._switch_tab("chats"))
        
        self.btn_tree = QPushButton("Дерево")
        self.btn_tree.setCheckable(True)
        self.btn_tree.setFixedHeight(32)
        self.btn_tree.clicked.connect(lambda: self._switch_tab("tree"))
        
        self.tab_group = QButtonGroup(self)
        self.tab_group.addButton(self.btn_chats)
        self.tab_group.addButton(self.btn_tree)
        
        tabs_layout.addWidget(self.btn_chats)
        tabs_layout.addWidget(self.btn_tree)
        layout.addLayout(tabs_layout)
        
        # Stacked widget for content
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        
        # Chats page
        chats_page = QWidget()
        chats_layout = QVBoxLayout(chats_page)
        chats_layout.setContentsMargins(5, 5, 5, 5)
        
        self.new_chat_btn = QPushButton("+ Новый чат")
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        chats_layout.addWidget(self.new_chat_btn)
        
        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._on_chat_clicked)
        chats_layout.addWidget(self.chat_list, 1)
        
        self.stack.addWidget(chats_page)
        
        # Tree page
        tree_page = QWidget()
        tree_layout = QVBoxLayout(tree_page)
        tree_layout.setContentsMargins(5, 5, 5, 5)
        
        # Client ID input
        client_layout = QHBoxLayout()
        client_layout.addWidget(QLabel("Client ID:"))
        self.client_id_edit = QLineEdit()
        self.client_id_edit.setPlaceholderText("Введите ID клиента")
        self.client_id_edit.setText("ngs")  # Default
        client_layout.addWidget(self.client_id_edit)
        tree_layout.addLayout(client_layout)
        
        self.selected_docs_label = QLabel("Выбрано документов: 0")
        tree_layout.addWidget(self.selected_docs_label)

        self.refresh_tree_btn = QPushButton("Загрузить дерево")
        self.refresh_tree_btn.clicked.connect(self._load_tree)
        tree_layout.addWidget(self.refresh_tree_btn)
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Название", "Тип"])
        self.tree_widget.setColumnWidth(0, 200)
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.itemSelectionChanged.connect(self._update_selected_docs)
        tree_layout.addWidget(self.tree_widget, 1)
        
        self.stack.addWidget(tree_page)
    
    def _switch_tab(self, tab: str):
        if tab == "chats":
            self.stack.setCurrentIndex(0)
            self.btn_chats.setChecked(True)
            self.btn_tree.setChecked(False)
        else:
            self.stack.setCurrentIndex(1)
            self.btn_chats.setChecked(False)
            self.btn_tree.setChecked(True)
    
    def _on_chat_clicked(self, item: QListWidgetItem):
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)
    
    def load_chats(self):
        if not self.client:
            return
        
        try:
            chats = self.client.list_chats(limit=50)
            self.chat_list.clear()
            
            for chat in chats:
                title = fix_mojibake(chat.title)
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, str(chat.id))
                self.chat_list.addItem(item)
        except Exception as e:
            logger.error(f"Error loading chats: {e}")
    
    def add_chat(self, chat_id: str, title: str):
        item = QListWidgetItem(title)
        item.setData(Qt.ItemDataRole.UserRole, chat_id)
        self.chat_list.insertItem(0, item)
        self.chat_list.setCurrentItem(item)
    
    def _load_tree(self):
        if not self.client:
            return
        
        client_id = self.client_id_edit.text().strip()
        if not client_id:
            QMessageBox.warning(self, "Ошибка", "Введите Client ID")
            return
        
        try:
            # Get projects tree from server
            tree_data = self.client.get_projects_tree(client_id=client_id)
            self.tree_widget.clear()
            
            if tree_data:
                for node in tree_data:
                    node_dict = node.model_dump() if hasattr(node, 'model_dump') else node.__dict__
                    self._add_tree_node(None, node_dict)
            else:
                QMessageBox.information(self, "Информация", "Дерево проектов пусто")
        except Exception as e:
            logger.error(f"Error loading tree: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить дерево: {e}")
    
    def _add_tree_node(self, parent, node: dict):
        name = fix_mojibake(node.get("name", ""))
        node_type = node.get("node_type", "")
        
        if parent is None:
            item = QTreeWidgetItem(self.tree_widget)
        else:
            item = QTreeWidgetItem(parent)
        
        item.setText(0, name)
        item.setText(1, node_type)
        item.setData(0, Qt.ItemDataRole.UserRole, node.get("id"))
        item.setData(0, Qt.ItemDataRole.UserRole + 1, node_type)
        
        children = node.get("children", [])
        for child in children:
            self._add_tree_node(item, child)

    def _update_selected_docs(self):
        doc_ids = self.get_selected_document_ids()
        self.selected_docs_label.setText(f"Выбрано документов: {len(doc_ids)}")

    def get_selected_document_ids(self) -> List[str]:
        selected = []
        for item in self.tree_widget.selectedItems():
            node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if node_type == "document":
                doc_id = item.data(0, Qt.ItemDataRole.UserRole)
                if doc_id:
                    selected.append(str(doc_id))
        return selected

    def get_client_id(self) -> str:
        return self.client_id_edit.text().strip()


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.client: Optional[AIZoomDocClient] = None
        
        self.setWindowTitle("AIZoomDoc Client")
        self.setMinimumSize(1200, 800)
        
        self._setup_menu()
        self._setup_ui()
        self._setup_statusbar()
        
        QTimer.singleShot(100, self._try_auto_login)
    
    def _setup_menu(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("Файл")
        
        login_action = QAction("Войти...", self)
        login_action.triggered.connect(self._show_login)
        file_menu.addAction(login_action)
        
        logout_action = QAction("Выйти", self)
        logout_action.triggered.connect(self._logout)
        file_menu.addAction(logout_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Закрыть", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        settings_menu = menubar.addMenu("Настройки")
        settings_action = QAction("Настройки...", self)
        settings_action.triggered.connect(self._show_settings)
        settings_menu.addAction(settings_action)
        
        help_menu = menubar.addMenu("Справка")
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel
        self.left_panel = LeftPanel()
        self.left_panel.setMinimumWidth(250)
        self.left_panel.setMaximumWidth(400)
        self.left_panel.chat_selected.connect(self._on_chat_selected)
        self.left_panel.new_chat_requested.connect(self._create_new_chat)
        splitter.addWidget(self.left_panel)
        
        # Chat widget
        self.chat_widget = ChatWidget()
        self.chat_widget.attachments_provider = self._get_message_context
        splitter.addWidget(self.chat_widget)
        
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)
    
    def _setup_statusbar(self):
        self.statusBar().showMessage("Не авторизован")
        self.user_label = QLabel("")
        self.statusBar().addPermanentWidget(self.user_label)
    
    def _try_auto_login(self):
        config = get_config_manager()
        if config.is_token_valid():
            try:
                self.client = AIZoomDocClient()
                user_info = self.client.get_me()
                self._on_login_success(user_info)
            except Exception as e:
                logger.info(f"Auto-login failed: {e}")
                self._show_login()
        else:
            self._show_login()
    
    def _show_login(self):
        dialog = LoginDialog(self)
        
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                if not self.client:
                    self.close()
                return
            
            server_url, token = dialog.get_credentials()
            if not server_url or not token:
                dialog.set_error("Заполните все поля")
                continue
            
            try:
                self.client = AIZoomDocClient(
                    server_url=server_url,
                    static_token=token
                )
                self.client.authenticate()
                user_info = self.client.get_me()
                self._on_login_success(user_info)
                break
            except AuthenticationError as e:
                dialog.set_error(f"Ошибка авторизации: {e.message}")
            except Exception as e:
                dialog.set_error(f"Ошибка: {e}")
    
    def _on_login_success(self, user_info: UserMeResponse):
        self.chat_widget.client = self.client
        self.left_panel.client = self.client
        
        username = fix_mojibake(user_info.user.username)
        self.statusBar().showMessage("Подключено")
        self.user_label.setText(f"{username} | {user_info.settings.model_profile}")
        
        self.left_panel.load_chats()
    
    def _logout(self):
        if self.client:
            self.client.logout()
            self.client = None
        
        self.left_panel.chat_list.clear()
        self.left_panel.tree_widget.clear()
        self.chat_widget.messages_area.clear()
        self.chat_widget.current_chat_id = None
        
        self.statusBar().showMessage("Не авторизован")
        self.user_label.setText("")
        self._show_login()
    
    def _show_settings(self):
        if not self.client:
            QMessageBox.warning(self, "Ошибка", "Сначала авторизуйтесь")
            return
        
        dialog = SettingsDialog(self.client, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                user_info = self.client.get_me()
                username = fix_mojibake(user_info.user.username)
                self.user_label.setText(f"{username} | {user_info.settings.model_profile}")
            except:
                pass
    
    def _show_about(self):
        QMessageBox.about(
            self,
            "О программе",
            "<h2>AIZoomDoc Client</h2>"
            "<p>Версия 2.0.0</p>"
            "<p>Клиент для анализа технической документации с помощью LLM.</p>"
        )
    
    def _on_chat_selected(self, chat_id: str):
        self.chat_widget.set_chat(chat_id)

    def _get_message_context(self) -> dict:
        """Получить client_id и выбранные документы для сообщения."""
        if not self.left_panel:
            return {}
        return {
            "client_id": self.left_panel.get_client_id(),
            "document_ids": self.left_panel.get_selected_document_ids()
        }
    
    def _create_new_chat(self):
        if not self.client:
            QMessageBox.warning(self, "Ошибка", "Сначала авторизуйтесь")
            return
        
        from PyQt6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getText(self, "Новый чат", "Название чата:")
        if not ok or not title.strip():
            return
        
        try:
            chat = self.client.create_chat(title=title.strip())
            self.left_panel.add_chat(str(chat.id), chat.title)
            self.chat_widget.set_chat(str(chat.id))
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось создать чат: {e}")


def run_gui():
    """Run GUI application."""
    if sys.platform == 'win32':
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    app = QApplication(sys.argv)
    app.setApplicationName("AIZoomDoc Client")
    app.setStyle("Fusion")
    
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    run_gui()
