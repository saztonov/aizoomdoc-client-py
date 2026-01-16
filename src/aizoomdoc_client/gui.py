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
    file_uploaded = pyqtSignal(str, str)  # filename, google_uri
    completed = pyqtSignal()
    
    def __init__(
        self,
        client: AIZoomDocClient,
        chat_id: str,
        message: str,
        document_ids: Optional[List[str]] = None,
        client_id: Optional[str] = None,
        local_files: Optional[List[str]] = None
    ):
        super().__init__()
        self.client = client
        self.chat_id = chat_id
        self.message = message
        self.document_ids = document_ids or []
        self.client_id = client_id
        self.local_files = local_files or []
        self._stop_requested = False
    
    def run(self):
        try:
            from uuid import UUID
            chat_uuid = UUID(self.chat_id)
            
            # Upload local files to Google File API first
            google_file_uris = []
            for file_path in self.local_files:
                if self._stop_requested:
                    break
                try:
                    self.phase_started.emit("upload", f"Загрузка {file_path}...")
                    result = self.client.upload_file_for_llm(file_path)
                    google_file_uris.append(result.google_file_uri)
                    self.file_uploaded.emit(result.filename, result.google_file_uri)
                except Exception as e:
                    logger.error(f"Failed to upload file {file_path}: {e}")
                    self.error_occurred.emit(f"Ошибка загрузки файла: {e}")
            
            doc_ids = [UUID(did) for did in self.document_ids] if self.document_ids else None
            for event in self.client.send_message(
                chat_uuid,
                self.message,
                attached_document_ids=doc_ids,
                client_id=self.client_id,
                google_file_uris=google_file_uris if google_file_uris else None
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
        self.attached_files: List[dict] = []  # List of attached files
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
        
        # Attachments panel
        self.attachments_panel = QWidget()
        attachments_layout = QHBoxLayout(self.attachments_panel)
        attachments_layout.setContentsMargins(0, 5, 0, 5)
        
        self.attachments_label = QLabel("Прикреплено: 0 файлов")
        self.attachments_label.setStyleSheet("color: #0066cc;")
        attachments_layout.addWidget(self.attachments_label)
        
        self.attachments_list = QLabel("")
        self.attachments_list.setStyleSheet("color: #666; font-size: 10px;")
        self.attachments_list.setWordWrap(True)
        attachments_layout.addWidget(self.attachments_list, 1)
        
        self.clear_attachments_btn = QPushButton("Очистить")
        self.clear_attachments_btn.setMaximumWidth(80)
        self.clear_attachments_btn.clicked.connect(self._clear_attachments)
        attachments_layout.addWidget(self.clear_attachments_btn)
        
        self.attachments_panel.setVisible(False)
        layout.addWidget(self.attachments_panel)
        
        # Input area with buttons
        input_container = QVBoxLayout()
        
        # Button row
        btn_row = QHBoxLayout()
        
        self.attach_file_btn = QPushButton("📎 Прикрепить файл")
        self.attach_file_btn.setMaximumWidth(150)
        self.attach_file_btn.clicked.connect(self._attach_file)
        btn_row.addWidget(self.attach_file_btn)
        
        self.attach_from_tree_btn = QPushButton("🌳 Из дерева")
        self.attach_from_tree_btn.setMaximumWidth(120)
        self.attach_from_tree_btn.setToolTip("Прикрепить выбранные документы из дерева проектов")
        self.attach_from_tree_btn.clicked.connect(self._attach_from_tree)
        btn_row.addWidget(self.attach_from_tree_btn)
        
        btn_row.addStretch()
        input_container.addLayout(btn_row)
        
        # Text input row
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
        
        input_container.addLayout(input_layout)
        layout.addLayout(input_container)
    
    def set_chat(self, chat_id: str):
        self.current_chat_id = chat_id
        self._load_history()
    
    def clear_for_new_chat(self):
        """Очистить виджет для нового чата (без записи в БД)."""
        self.current_chat_id = None
        self.messages_area.clear()
        self.input_edit.clear()
        self.status_label.setText("")
        self._clear_attachments()
    
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
        message = self.input_edit.toPlainText().strip()
        if not message:
            return
        
        # Если чата нет - создаём с названием из первых 100 символов сообщения
        if not self.current_chat_id:
            if not self.client:
                QMessageBox.warning(self, "Ошибка", "Сначала авторизуйтесь")
                return
            
            try:
                title = message[:100].strip()
                if len(message) > 100:
                    title += "..."
                chat = self.client.create_chat(title=title)
                self.current_chat_id = str(chat.id)
                # Уведомляем о создании нового чата (для обновления списка)
                if hasattr(self, 'on_chat_created') and callable(self.on_chat_created):
                    self.on_chat_created(self.current_chat_id, title)
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", f"Не удалось создать чат: {e}")
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
        
        # Collect document IDs from attachments
        document_ids = []
        local_files = []
        
        # From attached files in chat widget
        for att in self.attached_files:
            if att.get("type") == "tree" and att.get("doc_id"):
                document_ids.append(att["doc_id"])
            elif att.get("type") == "local" and att.get("path"):
                local_files.append(att["path"])
        
        # Also check tree selection via attachments_provider
        client_id = None
        if callable(self.attachments_provider):
            ctx = self.attachments_provider() or {}
            for doc_id in ctx.get("document_ids", []):
                if doc_id not in document_ids:
                    document_ids.append(doc_id)
            client_id = ctx.get("client_id")

        self.worker = StreamWorker(
            self.client,
            self.current_chat_id,
            message,
            document_ids=document_ids,
            client_id=client_id,
            local_files=local_files
        )
        self.worker.token_received.connect(self._on_token)
        self.worker.phase_started.connect(self._on_phase)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.completed.connect(self._on_completed)
        self.worker.start()
        
        # Clear attachments after sending
        self._clear_attachments()
    
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
    
    def _attach_file(self):
        """Attach a local file (MD, HTML, TXT)."""
        from PyQt6.QtWidgets import QFileDialog
        
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите файлы для прикрепления",
            "",
            "Документы (*.md *.html *.txt *.pdf);;Все файлы (*.*)"
        )
        
        for file_path in files:
            import os
            file_name = os.path.basename(file_path)
            self.attached_files.append({
                "type": "local",
                "path": file_path,
                "name": file_name
            })
        
        self._update_attachments_display()
    
    def _attach_from_tree(self):
        """Attach documents selected in the projects tree."""
        if not callable(self.attachments_provider):
            QMessageBox.warning(self, "Ошибка", "Дерево проектов недоступно")
            return
        
        ctx = self.attachments_provider() or {}
        doc_ids = ctx.get("document_ids", [])
        
        if not doc_ids:
            QMessageBox.information(self, "Информация", "Выберите документы в дереве проектов (вкладка 'Дерево')")
            return
        
        for doc_id in doc_ids:
            # Check if already attached
            if not any(f.get("doc_id") == doc_id for f in self.attached_files):
                self.attached_files.append({
                    "type": "tree",
                    "doc_id": doc_id,
                    "name": f"Документ {doc_id[:8]}..."
                })
        
        self._update_attachments_display()
    
    def _clear_attachments(self):
        """Clear all attachments."""
        self.attached_files.clear()
        self._update_attachments_display()
    
    def _update_attachments_display(self):
        """Update the attachments panel display."""
        count = len(self.attached_files)
        self.attachments_label.setText(f"Прикреплено: {count} файл(ов)")
        
        if count > 0:
            names = [f.get("name", "?") for f in self.attached_files]
            self.attachments_list.setText(", ".join(names))
            self.attachments_panel.setVisible(True)
        else:
            self.attachments_list.setText("")
            self.attachments_panel.setVisible(False)
    
    def add_attachment(self, doc_id: str, name: str):
        """Add a document attachment from external source."""
        if not any(f.get("doc_id") == doc_id for f in self.attached_files):
            self.attached_files.append({
                "type": "tree",
                "doc_id": doc_id,
                "name": name
            })
            self._update_attachments_display()
    
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
        self.client_id_edit.setPlaceholderText("Опционально (можно оставить пустым)")
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
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.setItemsExpandable(True)
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.itemSelectionChanged.connect(self._update_selected_docs)
        self.tree_widget.itemExpanded.connect(self._on_tree_item_expanded)
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
        
        try:
            # Get ALL projects tree nodes from server (like v1 app)
            client_id = self.client_id_edit.text().strip() or None
            tree_data = self.client.get_projects_tree(client_id=client_id, all_nodes=True)
            self.tree_widget.clear()
            
            if tree_data:
                # Build hierarchy from flat list (as in v1)
                nodes = []
                for node in tree_data:
                    node_dict = node.model_dump() if hasattr(node, 'model_dump') else node.__dict__
                    nodes.append(node_dict)

                # Create QTreeWidgetItem for each node
                node_items: dict[str, QTreeWidgetItem] = {}
                for node in nodes:
                    item = QTreeWidgetItem()
                    name = fix_mojibake(node.get("name", ""))
                    node_type = node.get("node_type", "")
                    item.setText(0, name)
                    item.setText(1, node_type)
                    item.setData(0, Qt.ItemDataRole.UserRole, node.get("id"))
                    item.setData(0, Qt.ItemDataRole.UserRole + 1, node_type)
                    node_items[str(node.get("id"))] = item

                # Build hierarchy by parent_id
                root_items = []
                for node in nodes:
                    item = node_items.get(str(node.get("id")))
                    parent_id = node.get("parent_id")
                    if parent_id and str(parent_id) in node_items:
                        node_items[str(parent_id)].addChild(item)
                    else:
                        root_items.append(item)

                # Add root items to tree
                for item in root_items:
                    self.tree_widget.addTopLevelItem(item)
                
                logger.info(f"Tree loaded: {len(nodes)} nodes, {len(root_items)} root items")
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
    
    def _on_tree_item_expanded(self, item: QTreeWidgetItem):
        """Lazy-load children when node is expanded."""
        if not self.client:
            return
        
        # Check if this item has a placeholder child
        if item.childCount() == 1 and item.child(0).text(0) == "...":
            # Remove placeholder
            item.takeChild(0)
            
            # Load actual children
            parent_id = item.data(0, Qt.ItemDataRole.UserRole)
            if not parent_id:
                return
            
            try:
                from uuid import UUID
                children = self.client.get_projects_tree(
                    client_id=self.client_id_edit.text().strip() or None,
                    parent_id=UUID(str(parent_id))
                )
                
                for child_node in children:
                    node_dict = child_node.model_dump() if hasattr(child_node, 'model_dump') else child_node.__dict__
                    child_item = QTreeWidgetItem()
                    name = fix_mojibake(node_dict.get("name", ""))
                    node_type = node_dict.get("node_type", "")
                    child_item.setText(0, name)
                    child_item.setText(1, node_type)
                    child_item.setData(0, Qt.ItemDataRole.UserRole, node_dict.get("id"))
                    child_item.setData(0, Qt.ItemDataRole.UserRole + 1, node_type)
                    
                    # Add placeholder if this child has children
                    if node_dict.get("children_count", 0) or node_dict.get("descendants_count", 0):
                        child_item.addChild(QTreeWidgetItem(["...", ""]))
                    
                    item.addChild(child_item)
            except Exception as e:
                logger.error(f"Error loading children: {e}")

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
        self.chat_widget.on_chat_created = self._on_new_chat_created
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
    
    def _on_new_chat_created(self, chat_id: str, title: str):
        """Добавить новый чат в список после его создания."""
        self.left_panel.add_chat(chat_id, title)

    def _get_message_context(self) -> dict:
        """Получить client_id и выбранные документы для сообщения."""
        if not self.left_panel:
            return {}
        return {
            "client_id": self.left_panel.get_client_id(),
            "document_ids": self.left_panel.get_selected_document_ids()
        }
    
    def _create_new_chat(self):
        """Открыть пустое окно для нового чата (запись в БД при первом сообщении)."""
        if not self.client:
            QMessageBox.warning(self, "Ошибка", "Сначала авторизуйтесь")
            return
        
        # Просто очищаем чат виджет, не создаём запись в БД
        self.chat_widget.clear_for_new_chat()
        # Снимаем выделение в списке чатов
        self.left_panel.chat_list.clearSelection()


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
