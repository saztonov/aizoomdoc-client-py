# -*- coding: utf-8 -*-
"""
Виджеты чата: сворачиваемые секции, пузыри сообщений, стриминг.
"""

import sys
import logging
import traceback
import base64
from typing import Optional

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QLabel, QTextBrowser, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QFont, QTextCursor, QPixmap, QDesktopServices

from aizoomdoc_client.markdown_formatter import format_message

logger = logging.getLogger(__name__)


def install_exception_hook():
    """Устанавливает глобальный обработчик необработанных исключений для PyQt6."""
    def _exception_hook(exc_type, exc_value, exc_tb):
        lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        msg = "".join(lines)
        logger.critical(f"Unhandled exception:\n{msg}")
        print(f"\n{'='*60}\nUnhandled exception:\n{msg}{'='*60}", flush=True)
        # Вызов дефолтного обработчика (чтобы Python мог завершить процесс)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _exception_hook


class CollapsibleSection(QFrame):
    """Сворачиваемый блок с заголовком-кнопкой и областью содержимого."""

    def __init__(self, title: str, parent=None, initially_expanded: bool = True):
        super().__init__(parent)
        self._title = title
        self._item_count = 0

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 2, 10, 2)
        main_layout.setSpacing(0)

        # Кнопка-заголовок
        self._toggle_btn = QPushButton()
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(initially_expanded)
        self._toggle_btn.clicked.connect(self._on_toggle)
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                border: none;
                background: #f0f4f8;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                color: #555;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton:hover {
                background: #e2e8f0;
            }
        """)
        main_layout.addWidget(self._toggle_btn)

        # Контейнер содержимого
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(10, 4, 0, 4)
        self._content_layout.setSpacing(2)
        main_layout.addWidget(self._content_widget)

        self._content_widget.setVisible(initially_expanded)
        self._update_label()

    def _on_toggle(self):
        expanded = self._toggle_btn.isChecked()
        self._content_widget.setVisible(expanded)
        self._update_label()

    def _update_label(self):
        arrow = "\u25bc" if self._toggle_btn.isChecked() else "\u25b6"
        count_text = f" ({self._item_count})" if self._item_count > 0 else ""
        self._toggle_btn.setText(f"{arrow}  {self._title}{count_text}")

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)
        self._item_count += 1
        self._update_label()

    def set_expanded(self, expanded: bool):
        self._toggle_btn.setChecked(expanded)
        self._content_widget.setVisible(expanded)
        self._update_label()

    def set_title(self, title: str):
        self._title = title
        self._update_label()

    @property
    def item_count(self) -> int:
        return self._item_count


class MessageBubbleWidget(QFrame):
    """Пузырь сообщения (пользователь или ассистент)."""

    def __init__(self, role: str, content: str, model_name: str = "", parent=None):
        super().__init__(parent)
        self._adjusting = False  # Защита от рекурсии при пересчёте высоты
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(0)

        bubble = QTextBrowser()
        bubble.setOpenExternalLinks(True)
        bubble.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setFont(QFont("Segoe UI", 11))
        self._bubble = bubble

        if role == "user":
            layout.addStretch(2)
            bubble.setStyleSheet("""
                QTextBrowser {
                    background: #e0e0e0; color: #333;
                    border: none; border-radius: 18px;
                    padding: 12px 16px;
                }
            """)
            html = (
                '<div style="font-size: 9px; color: #666; font-weight: bold; '
                'margin-bottom: 6px; text-align: right;">Пользователь</div>'
                f'<div style="white-space: pre-wrap; text-align: right;">{content}</div>'
            )
            bubble.setHtml(html)
            layout.addWidget(bubble, 8)
        else:
            formatted = format_message(content)
            label = model_name or "LLM"
            bubble.setStyleSheet("""
                QTextBrowser {
                    background: #ffffff; color: #333;
                    border: 1px solid #e0e0e0; border-radius: 18px;
                    padding: 12px 16px;
                }
            """)
            html = (
                f'<div style="font-size: 9px; color: #009933; font-weight: bold; '
                f'margin-bottom: 6px;">{label}</div>'
                f'<div>{formatted}</div>'
            )
            bubble.setHtml(html)
            layout.addWidget(bubble, 8)
            layout.addStretch(2)

        # Первоначальная подгонка высоты
        self._apply_height()

    def _apply_height(self):
        """Вычислить и применить высоту QTextBrowser по содержимому."""
        self._bubble.document().setTextWidth(self._bubble.viewport().width() or 400)
        doc_height = self._bubble.document().size().height()
        h = int(doc_height) + 30
        if h > 2000:
            self._bubble.setMaximumHeight(2000)
            self._bubble.setMinimumHeight(60)
            self._bubble.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self._bubble.setFixedHeight(max(h, 40))

    def resizeEvent(self, event):
        """Пересчитать высоту при изменении ширины виджета."""
        super().resizeEvent(event)
        if self._adjusting:
            return
        self._adjusting = True
        try:
            self._apply_height()
        finally:
            self._adjusting = False


class StreamingBubbleWidget(QFrame):
    """Виджет для стриминга токенов в реальном времени."""

    def __init__(self, model_name: str = "LLM", parent=None):
        super().__init__(parent)
        self._adjusting = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(0)

        self._text_browser = QTextBrowser()
        self._text_browser.setOpenExternalLinks(True)
        self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_browser.setFont(QFont("Segoe UI", 11))
        self._text_browser.setStyleSheet("""
            QTextBrowser {
                background: #ffffff; color: #333;
                border: 1px solid #e0e0e0; border-radius: 18px;
                padding: 12px 16px;
            }
        """)

        header = (
            f'<div style="font-size: 9px; color: #009933; font-weight: bold; '
            f'margin-bottom: 6px;">{model_name}</div><div>'
        )
        self._text_browser.setHtml(header)

        layout.addWidget(self._text_browser, 8)
        layout.addStretch(2)

        self._accumulated = ""

        # Дебаунс пересчёта высоты
        self._height_timer = QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.setInterval(50)
        self._height_timer.timeout.connect(self._adjust_height)

    def append_token(self, token: str):
        self._accumulated += token
        cursor = self._text_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(token)
        self._text_browser.setTextCursor(cursor)
        if not self._height_timer.isActive():
            self._height_timer.start()

    def get_accumulated_text(self) -> str:
        return self._accumulated

    def _adjust_height(self):
        if self._adjusting:
            return
        self._adjusting = True
        try:
            self._text_browser.document().setTextWidth(
                self._text_browser.viewport().width() or 400
            )
            doc_height = self._text_browser.document().size().height()
            h = int(doc_height) + 30
            if h > 2000:
                self._text_browser.setMaximumHeight(2000)
                self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            else:
                self._text_browser.setFixedHeight(max(h, 40))
        finally:
            self._adjusting = False


class SystemMessageWidget(QLabel):
    """Системное сообщение (фаза, успех, ошибка)."""

    _COLORS = {
        "info": "#6c757d",
        "progress": "#17a2b8",
        "warning": "#ffc107",
        "error": "#dc3545",
        "success": "#28a745",
    }

    def __init__(self, text: str, msg_type: str = "info", parent=None):
        super().__init__(text, parent)
        color = self._COLORS.get(msg_type, self._COLORS["info"])
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"color: {color}; font-size: 10px; font-style: italic; padding: 2px 0;"
        )


class ToolCallWidget(QFrame):
    """Виджет отображения tool call от LLM."""

    def __init__(self, tool: str, reason: str, params: dict, parent=None):
        super().__init__(parent)

        if tool == "request_images":
            bg = "#e8f4fc"
            border_color = "#0066cc"
            block_ids = params.get("block_ids", [])
            icon = "\U0001f5bc\ufe0f"
            title = "LLM запрашивает изображения"
            detail = f'<code>{", ".join(block_ids) if block_ids else "..."}</code>'
        elif tool == "zoom":
            bg = "#fff8e8"
            border_color = "#ff9900"
            block_id = params.get("block_id", "")
            bbox = params.get("bbox_norm", [])
            icon = "\U0001f50d"
            title = "LLM запрашивает детализацию"
            detail = f"<code>{block_id}</code> \u2192 bbox: {bbox}"
        else:
            bg = "#f0f0f0"
            border_color = "#999"
            icon = "\U0001f527"
            title = tool
            detail = str(params)

        self.setStyleSheet(
            f"background: {bg}; border-left: 3px solid {border_color}; "
            f"border-radius: 0; padding: 5px; margin: 2px 0;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        title_label = QLabel(f"<b>{icon} {title}:</b>")
        title_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        layout.addWidget(title_label)

        reason_label = QLabel(f'<span style="color: #666;">{reason}</span>')
        reason_label.setStyleSheet("font-size: 11px; background: transparent; border: none;")
        reason_label.setWordWrap(True)
        layout.addWidget(reason_label)

        detail_label = QLabel(detail)
        detail_label.setStyleSheet("font-size: 10px; background: transparent; border: none;")
        detail_label.setWordWrap(True)
        detail_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(detail_label)


class ImageWidget(QFrame):
    """Виджет для одного изображения с подписью."""

    def __init__(self, block_id: str, kind: str, pixmap: QPixmap, url: str, parent=None):
        super().__init__(parent)
        self._url = url

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        img_label = QLabel()
        if pixmap.width() > 400:
            scaled = pixmap.scaledToWidth(400, Qt.TransformationMode.SmoothTransformation)
        else:
            scaled = pixmap
        img_label.setPixmap(scaled)
        img_label.setCursor(Qt.CursorShape.PointingHandCursor)
        img_label.setStyleSheet("border: 1px solid #ccc;")
        img_label.mousePressEvent = lambda e: QDesktopServices.openUrl(QUrl(url))
        layout.addWidget(img_label)

        caption = QLabel(f"\U0001f4f7 {block_id} ({kind})")
        caption.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(caption)


class ImageErrorWidget(QFrame):
    """Виджет для ошибки загрузки изображения."""

    def __init__(self, block_id: str, error_text: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)

        label = QLabel(f"\u26a0\ufe0f {error_text}: {block_id}")
        label.setStyleSheet("color: #856404; font-size: 11px;")
        layout.addWidget(label)
