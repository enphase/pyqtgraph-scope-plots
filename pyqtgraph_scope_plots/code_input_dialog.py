# Copyright 2025 Enphase Energy, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.
from typing import Tuple, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QLabel, QDialogButtonBox, QTextEdit, QLineEdit


class CodeInputDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, label: str, initial: str = "", *, multiline: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)

        label_widget = QLabel()
        label_widget.setTextFormat(Qt.TextFormat.MarkdownText)
        label_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label_widget.setText(label)
        layout.addWidget(label_widget)

        if multiline:
            self._editor_widget: Union[QTextEdit, QLineEdit] = QTextEdit()
        else:
            self._editor_widget = QLineEdit()
        self._editor_widget.setText(initial)
        self._editor_widget.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self._editor_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @classmethod
    def getText(
        cls, parent: QWidget, title: str, label: str, initial: str = "", *, multiline: bool = False
    ) -> Tuple[str, bool]:
        dialog = cls(parent, title, label, initial, multiline=multiline)
        result = dialog.exec_()
        if isinstance(dialog._editor_widget, QTextEdit):
            text = dialog._editor_widget.toPlainText()
        elif isinstance(dialog._editor_widget, QLineEdit):
            text = dialog._editor_widget.text()
        else:
            raise TypeError
        return text, result == QDialog.DialogCode.Accepted
