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

# Fix encoding for Windows (with None check for PyInstaller windowed mode)
if sys.platform == 'win32':
    import codecs
    if sys.stdout is not None:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    if sys.stderr is not None:
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QComboBox, QSplitter,
    QListWidget, QListWidgetItem, QFrame, QScrollArea, QProgressBar,
    QMenuBar, QMenu, QDialog, QDialogButtonBox, QMessageBox,
    QGroupBox, QSizePolicy, QTabWidget, QTextBrowser, QStackedWidget,
    QStatusBar, QToolBar, QTreeWidget, QTreeWidgetItem, QButtonGroup,
    QDoubleSpinBox, QSpinBox, QFormLayout, QCheckBox, QStyle
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
    # Новые сигналы для полного логирования
    sse_event = pyqtSignal(str, dict)  # event_type, data
    tool_called = pyqtSignal(str, str, dict)  # tool_name, reason, parameters
    llm_final_received = pyqtSignal(str)  # final content
    thinking_received = pyqtSignal(str)  # thinking content
    image_ready = pyqtSignal(dict)  # image data: block_id, kind, url, reason
    
    def __init__(
        self,
        client: AIZoomDocClient,
        chat_id: str,
        message: str,
        document_ids: Optional[List[str]] = None,
        client_id: Optional[str] = None,
        local_files: Optional[List[str]] = None,
        tree_files: Optional[List[dict]] = None,
        compare_document_ids_a: Optional[List[str]] = None,
        compare_document_ids_b: Optional[List[str]] = None
    ):
        super().__init__()
        self.client = client
        self.chat_id = chat_id
        self.message = message
        self.document_ids = document_ids or []
        self.client_id = client_id
        self.local_files = local_files or []
        self.tree_files = tree_files or []
        self.compare_document_ids_a = compare_document_ids_a or []
        self.compare_document_ids_b = compare_document_ids_b or []
        self._stop_requested = False
        self._received_tokens = False
    
    def run(self):
        try:
            from uuid import UUID
            chat_uuid = UUID(self.chat_id)
            
            # Upload local files to Google File API first
            google_files = []
            for file_path in self.local_files:
                if self._stop_requested:
                    break
                try:
                    self.phase_started.emit("upload", f"Загрузка {file_path}...")
                    result = self.client.upload_file_for_llm(file_path)
                    # Передаём и URI, и mime_type
                    google_files.append({
                        "uri": result.google_file_uri,
                        "mime_type": result.mime_type,
                        "storage_path": result.storage_path
                    })
                    self.file_uploaded.emit(result.filename, result.google_file_uri)
                except Exception as e:
                    logger.error(f"Failed to upload file {file_path}: {e}")
                    self.error_occurred.emit(f"Ошибка загрузки файла: {e}")
            
            doc_ids = [UUID(did) for did in self.document_ids] if self.document_ids else None
            compare_a = [UUID(did) for did in self.compare_document_ids_a] if self.compare_document_ids_a else None
            compare_b = [UUID(did) for did in self.compare_document_ids_b] if self.compare_document_ids_b else None
            for event in self.client.send_message(
                chat_uuid,
                self.message,
                attached_document_ids=doc_ids,
                client_id=self.client_id,
                google_files=google_files if google_files else None,
                tree_files=self.tree_files if self.tree_files else None,
                compare_document_ids_a=compare_a,
                compare_document_ids_b=compare_b
            ):
                if self._stop_requested:
                    break
                
                # Отправляем все события для логирования
                print(f"[SSE] Event: {event.event}, Data keys: {list(event.data.keys()) if event.data else []}", flush=True)
                self.sse_event.emit(event.event, event.data)
                
                # Обработка событий очереди и статуса
                if event.event == "queue_position":
                    position = event.data.get("position", 0)
                    self.phase_started.emit("queue", f"Позиция в очереди: {position}")
                elif event.event == "processing_started":
                    self.phase_started.emit("processing", "Обработка началась...")
                elif event.event == "llm_token":
                    token = event.data.get("token", "")
                    if token:
                        self._received_tokens = True
                    self.token_received.emit(token)
                elif event.event == "phase_started":
                    phase = event.data.get("phase", "")
                    desc = event.data.get("description", "")
                    self.phase_started.emit(phase, desc)
                elif event.event == "tool_call":
                    tool = event.data.get("tool", "unknown")
                    reason = event.data.get("reason", "")
                    params = event.data.get("parameters", {})
                    self.tool_called.emit(tool, reason, params)
                elif event.event == "llm_thinking":
                    content = event.data.get("content", "")
                    if content:
                        self.thinking_received.emit(content)
                elif event.event == "image_ready":
                    logger.info(f"[DEBUG] image_ready event received: {event.data}")
                    print(f"[DEBUG] image_ready: {event.data}", flush=True)
                    self.image_ready.emit(event.data)
                elif event.event == "llm_final":
                    content = event.data.get("content", "")
                    self.llm_final_received.emit(content)
                    if content and not self._received_tokens:
                        self.token_received.emit(content)
                elif event.event == "error":
                    msg = event.data.get("message", "Unknown error")
                    self.error_occurred.emit(msg)
            
            self.sse_event.emit("completed", {})
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
        
        config = get_config_manager()
        saved_creds = config.load_static_token()
        
        # Server
        server_group = QGroupBox("Сервер")
        server_layout = QVBoxLayout(server_group)
        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText("http://localhost:8000")
        # Используем сохранённый URL или из конфига
        if saved_creds and saved_creds.get("server_url"):
            self.server_edit.setText(saved_creds["server_url"])
        else:
            self.server_edit.setText(config.get_config().server_url)
        server_layout.addWidget(self.server_edit)
        layout.addWidget(server_group)
        
        # Token
        token_group = QGroupBox("Статичный токен")
        token_layout = QHBoxLayout(token_group)
        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("Введите ваш статичный токен")
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Предзаполняем сохранённый токен
        if saved_creds and saved_creds.get("static_token"):
            self.token_edit.setText(saved_creds["static_token"])
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
        self.setMinimumWidth(550)
        
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
        
        # LLM Parameters
        llm_group = QGroupBox("Параметры LLM")
        llm_layout = QFormLayout(llm_group)
        
        # Temperature
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(1.0)
        self.temp_spin.setToolTip("Температура генерации (0=детерминированно, 2=максимально креативно)")
        llm_layout.addRow("Температура:", self.temp_spin)
        
        # Top-p
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setValue(0.95)
        self.top_p_spin.setToolTip("Top-p sampling (nucleus sampling)")
        llm_layout.addRow("Top-p:", self.top_p_spin)
        
        layout.addWidget(llm_group)
        
        # Thinking mode
        thinking_group = QGroupBox("Режим Thinking (Deep Think)")
        thinking_layout = QVBoxLayout(thinking_group)
        
        self.thinking_checkbox = QCheckBox("Включить режим Thinking")
        self.thinking_checkbox.setChecked(True)
        self.thinking_checkbox.setToolTip("Модель будет 'размышлять' перед ответом для более качественных результатов")
        thinking_layout.addWidget(self.thinking_checkbox)
        
        budget_layout = QHBoxLayout()
        budget_layout.addWidget(QLabel("Бюджет токенов:"))
        self.thinking_budget_spin = QSpinBox()
        self.thinking_budget_spin.setRange(0, 24576)
        self.thinking_budget_spin.setSingleStep(1024)
        self.thinking_budget_spin.setValue(0)
        self.thinking_budget_spin.setToolTip("0 = автоматически, иначе ограничение токенов на размышления")
        self.thinking_budget_spin.setSpecialValueText("Авто")
        budget_layout.addWidget(self.thinking_budget_spin)
        thinking_layout.addLayout(budget_layout)
        
        layout.addWidget(thinking_group)
        
        # Media resolution
        media_group = QGroupBox("Разрешение медиа")
        media_layout = QVBoxLayout(media_group)
        self.media_combo = QComboBox()
        self.media_combo.addItem("Низкое (быстрее, меньше токенов)", "low")
        self.media_combo.addItem("Среднее", "medium")
        self.media_combo.addItem("Высокое (лучшее качество)", "high")
        self.media_combo.setCurrentIndex(2)  # high по умолчанию
        media_layout.addWidget(self.media_combo)
        layout.addWidget(media_group)
        
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
            s = user_info.settings
            
            idx = self.model_combo.findData(s.model_profile)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            
            roles = self.client.get_available_roles()
            for role in roles:
                name = fix_mojibake(role.name)
                self.role_combo.addItem(name, role.id)
            
            if s.selected_role_prompt_id:
                idx = self.role_combo.findData(s.selected_role_prompt_id)
                if idx >= 0:
                    self.role_combo.setCurrentIndex(idx)
            
            # LLM параметры
            self.temp_spin.setValue(getattr(s, 'temperature', 1.0))
            self.top_p_spin.setValue(getattr(s, 'top_p', 0.95))
            self.thinking_checkbox.setChecked(getattr(s, 'thinking_enabled', True))
            self.thinking_budget_spin.setValue(getattr(s, 'thinking_budget', 0))
            
            media_res = getattr(s, 'media_resolution', 'high')
            idx = self.media_combo.findData(media_res)
            if idx >= 0:
                self.media_combo.setCurrentIndex(idx)
                
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
    
    def _save_and_accept(self):
        try:
            self.client.update_settings(
                model_profile=self.model_combo.currentData(),
                selected_role_prompt_id=self.role_combo.currentData(),
                temperature=self.temp_spin.value(),
                top_p=self.top_p_spin.value(),
                thinking_enabled=self.thinking_checkbox.isChecked(),
                thinking_budget=self.thinking_budget_spin.value(),
                media_resolution=self.media_combo.currentData()
            )
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e}")


class ChatWidget(QWidget):
    """Chat widget with messages."""
    
    # Сигнал при изменении модели
    model_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.client: Optional[AIZoomDocClient] = None
        self.current_chat_id: Optional[str] = None
        self.worker: Optional[StreamWorker] = None
        self.attachments_provider = None
        self.attached_files: List[dict] = []  # List of attached files
        self._accumulated_response = ""  # Для локального сохранения ответа
        self._pulse_state = 0  # Состояние анимации индикатора
        self._shown_phases = set()  # Отслеживание показанных фаз (чтобы не дублировать)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Top bar with model selector
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 5)
        
        top_bar.addWidget(QLabel("Режим:"))
        self.model_combo = QComboBox()
        self.model_combo.addItem("⚡ Простой (Flash)", "simple")
        self.model_combo.addItem("🧠 Сложный (Flash + Pro)", "complex")
        self.model_combo.setMinimumWidth(180)
        self.model_combo.setToolTip("Простой: быстрый ответ одной моделью\nСложный: двухэтапный анализ с более качественным результатом")
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        top_bar.addWidget(self.model_combo)
        
        top_bar.addStretch()
        layout.addLayout(top_bar)
        
        # Messages area
        self.messages_area = QTextBrowser()
        self.messages_area.setOpenExternalLinks(True)
        self.messages_area.setFont(QFont("Segoe UI", 11))
        layout.addWidget(self.messages_area, 1)
        
        # Status bar with progress indicator
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 2, 0, 2)

        # Progress indicator (пульсирующая точка)
        self.progress_indicator = QLabel("")
        self.progress_indicator.setFixedWidth(20)
        self.progress_indicator.setStyleSheet("color: #4CAF50; font-size: 14px;")
        self.progress_indicator.setVisible(False)
        status_layout.addWidget(self.progress_indicator)

        # Status label
        self.status_label = QLabel("")
        self._status_idle_style = "color: #666; font-style: italic;"
        self._status_active_style = "color: #0066cc; font-weight: bold;"
        self.status_label.setStyleSheet(self._status_idle_style)
        status_layout.addWidget(self.status_label, 1)

        layout.addLayout(status_layout)

        # Timer for progress indicator animation
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self._pulse_indicator)
        
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

        self.compare_mode_cb = QCheckBox("🔄 Сравнение")
        self.compare_mode_cb.setToolTip("Режим сравнения двух документов (DOC_A vs DOC_B)")
        btn_row.addWidget(self.compare_mode_cb)

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
    
    def _append_message(self, role: str, content: str, images: list = None, model_name: str = None):
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if role == "user":
            # Сообщение пользователя — справа, серый фон, скруглённые углы
            html = f'''
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 10px 0;">
                <tr>
                    <td width="20%"></td>
                    <td width="80%" align="right">
                        <div style="background: #e0e0e0; color: #333; 
                                    padding: 12px 16px; 
                                    border-radius: 18px 18px 4px 18px; 
                                    text-align: right;">
                            <div style="font-size: 9px; color: #666; font-weight: bold; margin-bottom: 6px;">Пользователь</div>
                            <div style="white-space: pre-wrap;">{content}</div>
                        </div>
                    </td>
                </tr>
            </table>
            '''
        elif role == "assistant":
            # Сообщение LLM — слева, белый фон с рамкой, скруглённые углы
            formatted = content.replace('\n', '<br>')
            # Определяем название модели
            llm_label = model_name if model_name else self._get_current_model_label()
            html = f'''
            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 10px 0;">
                <tr>
                    <td width="80%" align="left">
                        <div style="background: #ffffff; color: #333; 
                                    padding: 12px 16px; 
                                    border-radius: 18px 18px 18px 4px; 
                                    border: 1px solid #e0e0e0; text-align: left;">
                            <div style="font-size: 9px; color: #009933; font-weight: bold; margin-bottom: 6px;">{llm_label}</div>
                            <div>{formatted}</div>
                        </div>
                    </td>
                    <td width="20%"></td>
                </tr>
            </table>
            '''
        else:
            html = f'<p style="color: #666; text-align: center; font-style: italic;">{content}</p>'
        
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
                                img_bytes = response.content
                                img_data = base64.b64encode(img_bytes).decode('utf-8')
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
        self.status_label.setStyleSheet(self._status_active_style)
        self.status_label.setText("⏳ Диалог с LLM активен...")
        self.status_label.setVisible(True)

        # Сброс состояния для нового запроса
        self._accumulated_response = ""
        self._reset_shown_phases()
        self._start_progress_indicator()
        
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Начало ответа LLM (слева, белый фон, скруглённые углы)
        llm_label = self._get_current_model_label()
        cursor.insertHtml(f'''
        <table width="100%" cellpadding="0" cellspacing="0" style="margin: 10px 0;">
            <tr>
                <td width="80%" align="left">
                    <div style="background: #ffffff; color: #333; 
                                padding: 12px 16px; 
                                border-radius: 18px 18px 18px 4px; 
                                border: 1px solid #e0e0e0; text-align: left;">
                        <div style="font-size: 9px; color: #009933; font-weight: bold; margin-bottom: 6px;">{llm_label}</div>
                        <div>
        ''')
        self.messages_area.setTextCursor(cursor)
        
        # Collect document IDs from attachments
        document_ids = []
        local_files = []
        tree_files = []

        # From attached files in chat widget
        for att in self.attached_files:
            if att.get("type") == "tree" and att.get("doc_id"):
                document_ids.append(att["doc_id"])
            elif att.get("type") == "local" and att.get("path"):
                local_files.append(att["path"])
            elif att.get("type") == "tree_file" and att.get("r2_key"):
                tree_files.append({
                    "r2_key": att["r2_key"],
                    "file_type": att.get("file_type", "result_md")
                })

        # Also check tree selection via attachments_provider
        client_id = None
        if callable(self.attachments_provider):
            ctx = self.attachments_provider() or {}
            for doc_id in ctx.get("document_ids", []):
                if doc_id not in document_ids:
                    document_ids.append(doc_id)
            client_id = ctx.get("client_id")

        # Проверка режима сравнения
        compare_a = None
        compare_b = None
        if self.compare_mode_cb.isChecked():
            if len(document_ids) != 2:
                QMessageBox.warning(
                    self,
                    "Режим сравнения",
                    "Для сравнения нужно прикрепить ровно 2 документа.\n"
                    f"Сейчас прикреплено: {len(document_ids)}"
                )
                self.send_btn.setEnabled(True)
                return
            compare_a = [document_ids[0]]
            compare_b = [document_ids[1]]
            document_ids = []  # Очищаем, т.к. передаём через compare_*

        self.worker = StreamWorker(
            self.client,
            self.current_chat_id,
            message,
            document_ids=document_ids,
            client_id=client_id,
            local_files=local_files,
            tree_files=tree_files,
            compare_document_ids_a=compare_a,
            compare_document_ids_b=compare_b
        )
        self.worker.token_received.connect(self._on_token)
        self.worker.phase_started.connect(self._on_phase)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.completed.connect(self._on_completed)
        # Новые сигналы для полного логирования
        self.worker.sse_event.connect(self._on_sse_event)
        self.worker.tool_called.connect(self._on_tool_call)
        self.worker.llm_final_received.connect(self._on_llm_final)
        self.worker.file_uploaded.connect(self._on_file_uploaded)
        self.worker.thinking_received.connect(self._on_thinking)
        self.worker.image_ready.connect(self._on_image_ready)
        self.worker.start()
        
        # Clear attachments after sending
        self._clear_attachments()
    
    def _on_token(self, token: str):
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()
        # Накапливаем ответ для локального сохранения
        self._accumulated_response += token
    
    def _on_phase(self, phase: str, desc: str):
        """Обработка смены фазы обработки."""
        self.status_label.setStyleSheet(self._status_active_style)
        self.status_label.setText(f"[{phase}] {desc}")
        self._start_progress_indicator()

        # Маппинг фаз на читаемые сообщения для чата
        phase_messages = {
            "queue": "⏳ Ожидание в очереди...",
            "processing": "⚙️ Обработка запроса",
            "upload": "📤 Загрузка файлов",
            "intent_router": "🧠 Анализ намерения",
            "flash_collect": "📚 Сбор материалов (Flash)",
            "pro_answer": "✍️ Генерация ответа (Pro)",
            "search": "🔍 Поиск по документам",
            "llm": "💬 Генерация ответа",
        }

        # Определяем ключевую фазу по подстроке
        phase_key = None
        phase_lower = phase.lower()
        for key in phase_messages:
            if key in phase_lower:
                phase_key = key
                break

        # Показываем в чате только если фаза ещё не была показана
        if phase_key and phase_key not in self._shown_phases:
            self._shown_phases.add(phase_key)
            self._append_system_message(phase_messages[phase_key], "progress")
    
    def _on_error(self, error: str):
        """Обработка ошибки."""
        self._stop_progress_indicator()
        self.send_btn.setEnabled(True)

        # Понятные сообщения для известных ошибок
        error_messages = {
            "failed to obtain final answer":
                "Не удалось получить ответ. Возможно, файлы документа недоступны или повреждены.",
            "connection refused":
                "Сервер недоступен. Проверьте подключение.",
            "connection error":
                "Ошибка соединения с сервером.",
            "token expired":
                "Сессия истекла. Требуется повторная авторизация.",
            "timeout":
                "Превышено время ожидания ответа от сервера.",
            "no documents found":
                "Документы не найдены.",
        }

        # Ищем подходящее сообщение
        user_msg = error
        error_lower = error.lower()
        for key, msg in error_messages.items():
            if key in error_lower:
                user_msg = msg
                break

        self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
        self.status_label.setText(f"❌ {user_msg}")
        self._append_system_message(f"❌ Ошибка: {user_msg}", "error")
    
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

    def add_file_attachment(self, file_id: str, r2_key: str, file_type: str, file_name: str):
        """Добавить файл MD/HTML из дерева к запросу."""
        if not any(f.get("file_id") == file_id for f in self.attached_files):
            self.attached_files.append({
                "type": "tree_file",
                "file_id": file_id,
                "r2_key": r2_key,
                "file_type": file_type,
                "name": file_name
            })
            self._update_attachments_display()

    def _on_completed(self):
        """Обработка завершения ответа."""
        self._stop_progress_indicator()
        self.status_label.setStyleSheet(self._status_idle_style)
        self.status_label.setText("✅ Готово")
        self.send_btn.setEnabled(True)

        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        # Закрываем блок ответа LLM
        cursor.insertHtml('''
                        </div>
                    </div>
                </td>
                <td width="20%"></td>
            </tr>
        </table>
        ''')
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()

        # Показываем успешное завершение в чате
        self._append_system_message("✅ Ответ получен", "success")

        self._accumulated_response = ""
        self._reset_shown_phases()
    
    def _on_model_changed(self):
        """Изменение режима модели (сохраняется на сервере)."""
        if not self.client:
            return
        
        new_profile = self.model_combo.currentData()
        try:
            self.client.update_settings(model_profile=new_profile)
            self.model_changed.emit(new_profile)
            logger.info(f"Model profile changed to: {new_profile}")
        except Exception as e:
            logger.error(f"Error updating model profile: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось сменить режим модели: {e}")
    
    def _on_sse_event(self, event_type: str, data: dict):
        """Обработка SSE-событий (логирование отключено)."""
        pass
    
    def _on_tool_call(self, tool: str, reason: str, params: dict):
        """Обработка запроса инструмента от LLM (request_images, zoom)."""
        self._start_progress_indicator()

        # Отображаем в статусе
        self.status_label.setStyleSheet(self._status_active_style)
        if tool == "request_images":
            self.status_label.setText(f"🖼️ Запрос изображений: {reason[:50]}...")
        elif tool == "zoom":
            self.status_label.setText(f"🔍 Zoom (детализация): {reason[:50]}...")
        else:
            self.status_label.setText(f"🔧 {tool}: {reason[:50]}...")
        
        # Отображаем запрос на картинки в чате
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        if tool == "request_images":
            block_ids = params.get("block_ids", [])
            html = f'''
            <div style="margin: 5px 20px; padding: 5px; background: #e8f4fc; border-left: 3px solid #0066cc; font-size: 11px;">
                <b>🖼️ LLM запрашивает изображения:</b><br/>
                <span style="color: #666;">{reason}</span><br/>
                <code>{", ".join(block_ids) if block_ids else "..."}</code>
            </div>
            '''
            cursor.insertHtml(html)
        elif tool == "zoom":
            block_id = params.get("block_id", "")
            bbox = params.get("bbox_norm", [])
            html = f'''
            <div style="margin: 5px 20px; padding: 5px; background: #fff8e8; border-left: 3px solid #ff9900; font-size: 11px;">
                <b>🔍 LLM запрашивает детализацию:</b><br/>
                <span style="color: #666;">{reason}</span><br/>
                <code>{block_id}</code> → bbox: {bbox}
            </div>
            '''
            cursor.insertHtml(html)
        
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()
    
    def _on_llm_final(self, content: str):
        """Получен финальный ответ LLM (для логирования)."""
        # Уже логируется через _on_sse_event
        pass
    
    def _on_file_uploaded(self, filename: str, uri: str):
        """Файл загружен в Google File API."""
        self.status_label.setText(f"📎 Загружен: {filename}")
    
    def _on_thinking(self, content: str):
        """Получен фрагмент thinking (размышлений) от LLM."""
        # Отображаем в статусе что идёт размышление
        self.status_label.setStyleSheet(self._status_active_style)
        self.status_label.setText("💭 LLM размышляет...")
    
    def _on_image_ready(self, data: dict):
        """Изображение готово - отобразить в чате."""
        logger.info(f"[DEBUG] _on_image_ready called with: {data}")
        print(f"[DEBUG] _on_image_ready: {data}", flush=True)
        
        block_id = data.get("block_id", "")
        kind = data.get("kind", "preview")
        # Сервер может отправлять url или public_url
        url = data.get("url") or data.get("public_url", "")
        reason = data.get("reason", "")
        
        print(f"[DEBUG] Extracted url: {url}", flush=True)
        
        if not url:
            print(f"[DEBUG] URL is empty, skipping image", flush=True)
            return
        
        # Обновляем статус
        self.status_label.setText(f"🖼️ Получено изображение: {block_id} ({kind})")
        
        # Добавляем изображение в чат
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        try:
            import httpx
            import base64
            
            print(f"[DEBUG] Downloading image from {url}...", flush=True)
            response = httpx.get(url, timeout=30.0)
            print(f"[DEBUG] Response status: {response.status_code}", flush=True)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', 'image/png')
                img_bytes = response.content
                print(f"[DEBUG] Image size: {len(img_bytes)} bytes", flush=True)
                img_data = base64.b64encode(img_bytes).decode('utf-8')
                data_url = f"data:{content_type};base64,{img_data}"
                
                # Вставляем изображение как отдельный блок с кликабельной ссылкой
                html = f'<br/><a href="{url}"><img src="{data_url}" width="400" style="max-width: 100%; border: 1px solid #ccc;"/></a><br/><small style="color: #888;">📷 {block_id} ({kind})</small><br/>'
                
                print(f"[DEBUG] Inserting image...", flush=True)
                cursor.insertHtml(html)
                self.messages_area.setTextCursor(cursor)
                self.messages_area.ensureCursorVisible()
                print(f"[DEBUG] Image inserted successfully", flush=True)
            else:
                print(f"[DEBUG] Failed to download: HTTP {response.status_code}", flush=True)
                # При ошибке показываем текст (не ссылку)
                html = f'<br/><span style="color: #856404;">⚠️ Ошибка загрузки {block_id} (HTTP {response.status_code})</span><br/>'
                cursor.insertHtml(html)
                self.messages_area.setTextCursor(cursor)
                self.messages_area.ensureCursorVisible()
                
        except Exception as e:
            print(f"[DEBUG] Exception: {e}", flush=True)
            logger.error(f"Error loading image {url}: {e}")
            html = f'<br/><span style="color: #cc0000;">❌ Ошибка: {block_id}</span><br/>'
            cursor.insertHtml(html)
            self.messages_area.setTextCursor(cursor)
    
    def load_model_setting(self):
        """Загрузить текущий режим модели с сервера."""
        if not self.client:
            return
        
        try:
            user_info = self.client.get_me()
            profile = user_info.settings.model_profile
            idx = self.model_combo.findData(profile)
            if idx >= 0:
                # Блокируем сигнал, чтобы не отправлять update на сервер
                self.model_combo.blockSignals(True)
                self.model_combo.setCurrentIndex(idx)
                self.model_combo.blockSignals(False)
        except Exception as e:
            logger.error(f"Error loading model setting: {e}")
    
    def _get_current_model_label(self) -> str:
        """Получить название текущей модели для отображения."""
        profile = self.model_combo.currentData()
        if profile == "simple":
            return "Gemini Flash"
        elif profile == "complex":
            return "Gemini Pro"
        return "LLM"

    # ==================== Progress Indicator Methods ====================

    def _start_progress_indicator(self):
        """Запустить анимацию индикатора процесса."""
        self.progress_indicator.setVisible(True)
        if not self.pulse_timer.isActive():
            self.pulse_timer.start(400)  # каждые 400мс

    def _stop_progress_indicator(self):
        """Остановить анимацию индикатора процесса."""
        self.pulse_timer.stop()
        self.progress_indicator.setVisible(False)
        self._pulse_state = 0

    def _pulse_indicator(self):
        """Анимация пульсации индикатора."""
        symbols = ["◐", "◓", "◑", "◒"]  # Вращающийся индикатор
        self._pulse_state = (self._pulse_state + 1) % len(symbols)
        self.progress_indicator.setText(symbols[self._pulse_state])

    # ==================== System Messages ====================

    def _append_system_message(self, text: str, msg_type: str = "info"):
        """Добавить системное сообщение в чат (стадии обработки, ошибки).

        Args:
            text: Текст сообщения
            msg_type: Тип сообщения (info, progress, warning, error, success)
        """
        colors = {
            "info": "#6c757d",      # серый
            "progress": "#17a2b8",   # синий
            "warning": "#ffc107",    # жёлтый
            "error": "#dc3545",      # красный
            "success": "#28a745"     # зелёный
        }
        color = colors.get(msg_type, colors["info"])

        html = f'''
        <table width="100%"><tr>
            <td align="center" style="padding: 2px 0;">
                <span style="color: {color}; font-size: 10px; font-style: italic;">
                    {text}
                </span>
            </td>
        </tr></table>
        '''
        cursor = self.messages_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self.messages_area.setTextCursor(cursor)
        self.messages_area.ensureCursorVisible()

    def _reset_shown_phases(self):
        """Сбросить отслеживание показанных фаз (вызывать при отправке нового сообщения)."""
        self._shown_phases.clear()


class LeftPanel(QWidget):
    """Left panel with Chats/Tree tabs."""
    
    chat_selected = pyqtSignal(str)  # chat_id
    new_chat_requested = pyqtSignal()
    chat_delete_requested = pyqtSignal(str)  # chat_id для удаления
    files_selected = pyqtSignal(list)  # Список файлов MD/HTML для прикрепления к запросу
    
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
        # Контекстное меню для удаления чата
        self.chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._on_chat_context_menu)
        chats_layout.addWidget(self.chat_list, 1)
        
        self.stack.addWidget(chats_page)
        
        # Tree page
        tree_page = QWidget()
        tree_layout = QVBoxLayout(tree_page)
        tree_layout.setContentsMargins(5, 5, 5, 5)
        
        # Header with refresh button
        header_layout = QHBoxLayout()
        self.selected_docs_label = QLabel("Выбрано документов: 0")
        header_layout.addWidget(self.selected_docs_label)
        header_layout.addStretch()
        self.refresh_tree_btn = QPushButton("↻")
        self.refresh_tree_btn.setFixedSize(28, 28)
        self.refresh_tree_btn.setToolTip("Обновить дерево")
        self.refresh_tree_btn.clicked.connect(self._load_tree)
        header_layout.addWidget(self.refresh_tree_btn)
        tree_layout.addLayout(header_layout)

        # Flag to track if tree was loaded
        self._tree_loaded = False

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Название"])
        self.tree_widget.setColumnWidth(0, 200)
        self.tree_widget.setRootIsDecorated(True)
        self.tree_widget.setItemsExpandable(True)
        self.tree_widget.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree_widget.itemSelectionChanged.connect(self._update_selected_docs)
        self.tree_widget.itemExpanded.connect(self._on_tree_item_expanded)
        self.tree_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self._on_tree_context_menu)
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
            # Auto-load tree on first switch
            if not self._tree_loaded and self.client:
                self._load_tree()
    
    def _on_chat_clicked(self, item: QListWidgetItem):
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        if chat_id:
            self.chat_selected.emit(chat_id)
    
    def _on_chat_context_menu(self, position):
        """Контекстное меню для списка чатов."""
        item = self.chat_list.itemAt(position)
        if not item:
            return
        
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        if not chat_id:
            return
        
        menu = QMenu(self)
        delete_action = menu.addAction("Удалить")
        delete_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon))
        
        action = menu.exec(self.chat_list.mapToGlobal(position))
        
        if action == delete_action:
            # Удаляем из списка сразу
            row = self.chat_list.row(item)
            self.chat_list.takeItem(row)
            # Отправляем сигнал для удаления на сервере и локально
            self.chat_delete_requested.emit(chat_id)
    
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
    
    def _format_node_display_name(self, node: dict) -> str:
        """Форматировать имя узла: (code) name или просто name."""
        name = fix_mojibake(node.get("name", ""))
        code = node.get("code")
        if code:
            return f"({code}) {name}"
        return name

    def _load_tree(self):
        if not self.client:
            return

        try:
            # Get ALL projects tree nodes from server with files (MD, HTML)
            tree_data = self.client.get_projects_tree(
                client_id=None,
                all_nodes=True,
                include_files=True  # Включить файлы результатов (MD, HTML)
            )
            self.tree_widget.clear()
            self._tree_loaded = True

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
                    node_type = node.get("node_type", "")
                    item.setText(0, self._format_node_display_name(node))
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

                # Add files as children of document nodes
                files_count = 0
                for node in nodes:
                    if node.get("node_type") == "document" and node.get("files"):
                        parent_item = node_items.get(str(node.get("id")))
                        if parent_item:
                            for file_info in node.get("files", []):
                                file_item = QTreeWidgetItem()
                                file_name = fix_mojibake(file_info.get("file_name", ""))
                                file_type = file_info.get("file_type", "")
                                file_item.setText(0, file_name)
                                file_item.setData(0, Qt.ItemDataRole.UserRole, file_info.get("id"))
                                file_item.setData(0, Qt.ItemDataRole.UserRole + 1, file_type)
                                # Store r2_key for potential download
                                file_item.setData(0, Qt.ItemDataRole.UserRole + 2, file_info.get("r2_key"))
                                parent_item.addChild(file_item)
                                files_count += 1

                # Add root items to tree
                for item in root_items:
                    self.tree_widget.addTopLevelItem(item)

                logger.info(f"Tree loaded: {len(nodes)} nodes, {len(root_items)} root items, {files_count} files")
            else:
                QMessageBox.information(self, "Информация", "Дерево проектов пусто")
        except Exception as e:
            logger.error(f"Error loading tree: {e}")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить дерево: {e}")
    
    def _add_tree_node(self, parent, node: dict):
        node_type = node.get("node_type", "")

        if parent is None:
            item = QTreeWidgetItem(self.tree_widget)
        else:
            item = QTreeWidgetItem(parent)

        item.setText(0, self._format_node_display_name(node))
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
                    client_id=None,
                    parent_id=UUID(str(parent_id))
                )

                for child_node in children:
                    node_dict = child_node.model_dump() if hasattr(child_node, 'model_dump') else child_node.__dict__
                    child_item = QTreeWidgetItem()
                    node_type = node_dict.get("node_type", "")
                    child_item.setText(0, self._format_node_display_name(node_dict))
                    child_item.setData(0, Qt.ItemDataRole.UserRole, node_dict.get("id"))
                    child_item.setData(0, Qt.ItemDataRole.UserRole + 1, node_type)

                    # Add placeholder if this child has children
                    if node_dict.get("children_count", 0) or node_dict.get("descendants_count", 0):
                        child_item.addChild(QTreeWidgetItem(["..."]))

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

    def get_selected_files(self) -> List[dict]:
        """Получить выбранные файлы MD/HTML из дерева."""
        selected = []
        for item in self.tree_widget.selectedItems():
            file_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if file_type in ("result_md", "ocr_html"):
                file_id = item.data(0, Qt.ItemDataRole.UserRole)
                r2_key = item.data(0, Qt.ItemDataRole.UserRole + 2)
                file_name = item.text(0)
                if file_id and r2_key:
                    selected.append({
                        "file_id": str(file_id),
                        "r2_key": r2_key,
                        "file_type": file_type,
                        "file_name": file_name
                    })
        return selected

    def _on_tree_context_menu(self, position):
        """Контекстное меню для элементов дерева."""
        item = self.tree_widget.itemAt(position)
        if not item:
            return

        node_type = item.data(0, Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)

        # Для файлов MD/HTML - добавить к запросу
        if node_type in ("result_md", "ocr_html"):
            type_label = "MD" if node_type == "result_md" else "HTML"
            add_action = menu.addAction(f"Добавить {type_label} к запросу")

            action = menu.exec(self.tree_widget.mapToGlobal(position))
            if action == add_action:
                file_id = item.data(0, Qt.ItemDataRole.UserRole)
                r2_key = item.data(0, Qt.ItemDataRole.UserRole + 2)
                file_name = item.text(0)
                if file_id and r2_key:
                    self.files_selected.emit([{
                        "file_id": str(file_id),
                        "r2_key": r2_key,
                        "file_type": node_type,
                        "file_name": file_name
                    }])

        # Для документов - добавить дочерние файлы
        elif node_type == "document":
            add_md_action = menu.addAction("Добавить MD к запросу")
            add_html_action = menu.addAction("Добавить HTML к запросу")
            add_all_action = menu.addAction("Добавить все файлы к запросу")

            action = menu.exec(self.tree_widget.mapToGlobal(position))
            if action:
                self._add_document_files_to_request(item, action, add_md_action, add_html_action, add_all_action)

    def _add_document_files_to_request(self, doc_item, action, md_action, html_action, all_action):
        """Добавить файлы из документа к запросу."""
        files = []
        for i in range(doc_item.childCount()):
            child = doc_item.child(i)
            child_type = child.data(0, Qt.ItemDataRole.UserRole + 1)

            if child_type in ("result_md", "ocr_html"):
                include = (
                    action == all_action or
                    (action == md_action and child_type == "result_md") or
                    (action == html_action and child_type == "ocr_html")
                )
                if include:
                    file_id = child.data(0, Qt.ItemDataRole.UserRole)
                    r2_key = child.data(0, Qt.ItemDataRole.UserRole + 2)
                    file_name = child.text(0)
                    if file_id and r2_key:
                        files.append({
                            "file_id": str(file_id),
                            "r2_key": r2_key,
                            "file_type": child_type,
                            "file_name": file_name
                        })

        if files:
            self.files_selected.emit(files)


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
        
        settings_menu.addSeparator()
        
        folder_action = QAction("Выбор папки для данных...", self)
        folder_action.triggered.connect(self._choose_data_folder)
        settings_menu.addAction(folder_action)
        
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
        self.left_panel.chat_delete_requested.connect(self._on_chat_delete)
        self.left_panel.files_selected.connect(self._on_files_selected)
        splitter.addWidget(self.left_panel)
        
        # Chat widget
        self.chat_widget = ChatWidget()
        self.chat_widget.attachments_provider = self._get_message_context
        self.chat_widget.on_chat_created = self._on_new_chat_created
        self.chat_widget.model_changed.connect(self._on_model_changed)
        splitter.addWidget(self.chat_widget)
        
        splitter.setSizes([300, 900])
        layout.addWidget(splitter)
    
    def _setup_statusbar(self):
        self.statusBar().showMessage("Не авторизован")
        self.user_label = QLabel("")
        self.statusBar().addPermanentWidget(self.user_label)
    
    def _try_auto_login(self):
        config = get_config_manager()
        
        # Сначала проверяем JWT токен
        if config.is_token_valid():
            try:
                self.client = AIZoomDocClient()
                user_info = self.client.get_me()
                self._on_login_success(user_info)
                return
            except Exception as e:
                logger.info(f"Auto-login with JWT failed: {e}")
        
        # Пробуем загрузить сохранённый статичный токен из локальной папки
        saved_creds = config.load_static_token()
        if saved_creds:
            try:
                self.client = AIZoomDocClient(
                    server_url=saved_creds["server_url"],
                    static_token=saved_creds["static_token"]
                )
                self.client.authenticate()
                user_info = self.client.get_me()
                self._on_login_success(user_info)
                return
            except Exception as e:
                logger.info(f"Auto-login with saved token failed: {e}")

        # Пробуем встроенные credentials (для production exe)
        default_creds = config.get_default_credentials()
        if default_creds:
            try:
                self.client = AIZoomDocClient(
                    server_url=default_creds["server_url"],
                    static_token=default_creds["static_token"]
                )
                self.client.authenticate()
                user_info = self.client.get_me()
                # Сохраняем для будущих запусков
                config.save_static_token(
                    default_creds["static_token"],
                    default_creds["server_url"]
                )
                self._on_login_success(user_info)
                return
            except Exception as e:
                logger.info(f"Auto-login with default credentials failed: {e}")

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
                
                # Сохраняем статичный токен в локальную папку
                config = get_config_manager()
                config.save_static_token(token, server_url)
                
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
        
        # Загрузить текущий режим модели в селектор
        self.chat_widget.load_model_setting()
        
        self.left_panel.load_chats()
    
    def _logout(self):
        if self.client:
            self.client.logout()
            self.client = None
        
        # Очищаем сохранённый токен
        config = get_config_manager()
        config.clear_static_token()
        
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
    
    def _on_chat_delete(self, chat_id: str):
        """Удалить чат - отправить на сервер и удалить локальные файлы."""
        if not self.client:
            return
        
        # Если это текущий чат - очистить виджет
        if self.chat_widget.current_chat_id == chat_id:
            self.chat_widget.clear_for_new_chat()
        
        # Отправить запрос на сервер (асинхронно)
        try:
            from uuid import UUID
            self.client.delete_chat(UUID(chat_id))
            logger.info(f"Chat deletion requested: {chat_id}")
        except Exception as e:
            logger.error(f"Error requesting chat deletion: {e}")
        
        # Удалить локальные файлы
        config = get_config_manager()
        config.delete_chat_data(chat_id)
    
    def _on_new_chat_created(self, chat_id: str, title: str):
        """Добавить новый чат в список после его создания."""
        self.left_panel.add_chat(chat_id, title)

    def _on_files_selected(self, files: list):
        """Обработать выбор файлов MD/HTML из дерева."""
        for f in files:
            self.chat_widget.add_file_attachment(
                file_id=f["file_id"],
                r2_key=f["r2_key"],
                file_type=f["file_type"],
                file_name=f["file_name"]
            )

    def _get_message_context(self) -> dict:
        """Получить выбранные документы для сообщения."""
        if not self.left_panel:
            return {}
        return {
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
    
    def _choose_data_folder(self):
        """Выбор папки для локального сохранения данных (чаты, картинки)."""
        from PyQt6.QtWidgets import QFileDialog
        
        config = get_config_manager()
        current_dir = str(config.get_data_dir())
        
        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для локальных данных",
            current_dir,
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            config.set_data_dir(folder)
            QMessageBox.information(
                self,
                "Папка выбрана",
                f"Локальные данные будут сохраняться в:\n{folder}\n\n"
                "Структура папок:\n"
                "  └─ chats/<chat_id>/\n"
                "      ├─ chat.log (лог сообщений)\n"
                "      └─ crops/ (изображения)"
            )
    
    def _on_model_changed(self, new_profile: str):
        """Обновить отображение режима модели в статусбаре."""
        if self.client:
            try:
                user_info = self.client.get_me()
                username = fix_mojibake(user_info.user.username)
                self.user_label.setText(f"{username} | {new_profile}")
            except:
                pass


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
