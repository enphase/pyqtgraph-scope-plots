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

from typing import Any

from PySide6.QtCore import QKeyCombination, QPoint
from PySide6.QtGui import QAction, Qt, QFocusEvent, QCloseEvent
from PySide6.QtWidgets import QWidget, QLineEdit, QHBoxLayout, QLabel, QMenu

from .signals_table import ContextMenuSignalsTable


class FilterOverlay(QWidget):
    def __init__(self, table: "FilterSignalsTable"):
        super().__init__(table)
        self._table = table
        self.setAutoFillBackground(True)

        self._filter_input = QLineEdit(self)
        self._filter_input.setMinimumWidth(200)
        self._filter_input.setMaximumWidth(200)
        self._filter_input.setPlaceholderText("filter")
        self._filter_input.textEdited.connect(self._on_filter)

        self._close_action = QAction("Close", self)
        self._close_action.setShortcut(Qt.Key.Key_Escape)
        self._close_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._close_action.triggered.connect(self._on_close)
        self.addAction(self._close_action)

        self._results = QLabel("")
        self._results.setMinimumWidth(0)

        layout = QHBoxLayout(self)
        layout.addWidget(self._filter_input)
        layout.addWidget(self._results)
        layout.setContentsMargins(0, 0, 0, 0)

    def start(self) -> None:
        """Re-initialize the filter overlay, eg when it is re-opened"""
        self._filter_input.setText("")
        self._results.setText("")
        self.show()
        self.setFocus()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self._filter_input.setFocus()

    def _on_close(self) -> None:
        self.close()
        self._table.setFocus()  # revert focus to parent

    def closeEvent(self, event: QCloseEvent) -> None:
        super().closeEvent(event)
        self._table._apply_filter("")  # clear filters on close

    def _on_filter(self, text: str) -> None:
        count = self._table._apply_filter(text)

        if not text:
            self._results.setText("")
        elif count == 0:  # no results
            self._results.setText(f"no matches")
        else:
            self._results.setText(f"{count} matches")
        self.adjustSize()


class FilterSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds filtering capability for signals via Ctrl+F."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._filter_action = QAction("Filter", self)
        self._filter_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_F))
        self._filter_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # require widget focus to fire
        self._filter_action.triggered.connect(self._on_filter)
        self.addAction(self._filter_action)

        self._filter_overlay = FilterOverlay(self)
        self._filter_overlay.hide()

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._filter_action)

    def _on_filter(self) -> FilterOverlay:
        self._filter_overlay.move(QPoint(0, 0))
        self._filter_overlay.start()
        return self._filter_overlay

    def _apply_filter(self, text: str) -> int:
        """Applies a filter on the rows, returning the number of matching rows. Use empty-string to clear filters."""
        text_elts = text.lower().split()
        matches = 0
        for row in range(0, self.rowCount()):
            item = self.item(row, self.COL_NAME)
            if item and ((not text) or all(text_elt in item.text().lower() for text_elt in text_elts)):
                self.showRow(row)
                matches += 1
            else:
                self.hideRow(row)
        return matches

    def _update(self) -> None:
        super()._update()
        self._filter_overlay.hide()  # clear the filter on an update, which regenerates the table
