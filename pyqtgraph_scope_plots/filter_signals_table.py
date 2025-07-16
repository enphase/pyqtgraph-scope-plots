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

import math
from functools import partial
from typing import Any, List

from PySide6.QtCore import QKeyCombination, QPoint
from PySide6.QtGui import QAction, Qt, QFocusEvent
from PySide6.QtWidgets import QWidget, QLineEdit, QHBoxLayout, QPushButton, QLabel, QTableWidgetItem, QMenu

from .signals_table import ContextMenuSignalsTable, SignalsTable


class FilterOverlay(QWidget):
    def __init__(self, table: "FilterSignalsTable"):
        super().__init__(table)
        self._table = table
        self.setWindowFlags(Qt.WindowType.Popup)

        self._filter_input = QLineEdit(self)
        self._filter_input.setMinimumWidth(200)
        self._filter_input.setMaximumWidth(200)
        self._filter_input.setPlaceholderText("filter")
        self._filter_input.textEdited.connect(partial(self._on_filter, 0))
        self._filter_input.returnPressed.connect(partial(self._on_filter, 1))  # same as next

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

    def focusInEvent(self, event: QFocusEvent, /) -> None:
        self._filter_input.setFocus()

    def _on_filter(self) -> None:
        text = self._filter_input.text()
        count = self._table._apply_filter(text)

        if not text:
            self._results.setText("")
            self.adjustSize()
            return

        if count == 0:  # no results
            self._results.setText(f"no matches")
            self.adjustSize()
            return  # specifically don't alter the user's selection
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
        self._filter_overlay.move(self.mapToGlobal(QPoint(0, 0)))
        self._filter_overlay.start()
        self._filter_overlay.show()
        self._filter_overlay.setFocus()
        return self._filter_overlay

    def _apply_filter(self, text: str) -> int:
        """Applies a filter on the rows, returning the number of matching rows. Use empty-string to clear filters."""

        # start scanning results at the last of the user's selection
        selected_rows = [item.row() for item in self._table.selectedItems()]
        if selected_rows:
            start_row = max(selected_rows)
        else:
            start_row = 0

        match_items: List[QTableWidgetItem] = []
        row_range = list(range(0, self._table.rowCount()))
        row_range = row_range[start_row:] + row_range[:start_row]
        for row in row_range:
            item = self._table.item(row, self._table.COL_NAME)
            if item and text in item.text().lower():
                match_items.append(item)

    def _update(self) -> None:
        super()._update()
        self._filter_overlay.hide()  # clear the filter on an update, which regenerates the table
