from typing import Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QTextEdit


class CodeInputDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, label: str, initial: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)

        label_widget = QLabel()
        label_widget.setTextFormat(Qt.TextFormat.MarkdownText)
        label_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label_widget.setText(label)
        layout.addWidget(label_widget)

        self._editor_widget = QTextEdit()
        self._editor_widget.setText(initial)
        self._editor_widget.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self._editor_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @classmethod
    def getText(cls, parent: QWidget, title: str, label: str, initial: str = "") -> Tuple[str, bool]:
        dialog = cls(parent, title, label, initial)
        result = dialog.exec_()
        if result == QDialog.DialogCode.Accepted:
            return dialog._editor_widget.toPlainText(), True
        else:
            return dialog._editor_widget.toPlainText(), False
