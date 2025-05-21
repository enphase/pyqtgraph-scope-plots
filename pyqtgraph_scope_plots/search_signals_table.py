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


class SearchOverlay(QWidget):
    def __init__(self, table: SignalsTable):
        super().__init__(table)
        self._table = table
        self.setWindowFlags(Qt.WindowType.Popup)

        self._search_input = QLineEdit(self)
        self._search_input.setMinimumWidth(200)
        self._search_input.setMaximumWidth(200)
        self._search_input.setPlaceholderText("search")
        self._search_input.textEdited.connect(partial(self._on_search, 0))
        self._search_input.returnPressed.connect(partial(self._on_search, 1))  # same as next

        self._prev_button = QPushButton("↑")
        self._prev_button.setMaximumWidth(20)
        self._prev_button.clicked.connect(partial(self._on_search, -1))
        self._next_button = QPushButton("↓")
        self._next_button.setMaximumWidth(20)
        self._next_button.clicked.connect(partial(self._on_search, 1))

        self._results = QLabel("")
        self._results.setMinimumWidth(0)

        layout = QHBoxLayout(self)
        layout.addWidget(self._search_input)
        layout.addWidget(self._prev_button)
        layout.addWidget(self._next_button)
        layout.addWidget(self._results)
        layout.setContentsMargins(0, 0, 0, 0)

    def start(self) -> None:
        """Re-initialize the search overlay, eg when it is re-opened"""
        self._search_input.setText("")
        self._results.setText("")

    def focusInEvent(self, event: QFocusEvent, /) -> None:
        self._search_input.setFocus()

    def _on_search(self, incr: int = 0, dummy: Any = None) -> None:
        text = self._search_input.text().lower()

        if not text:
            self._results.setText("")
            self.adjustSize()
            return

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

        if not match_items:  # no results
            self._results.setText(f"no matches")
            self.adjustSize()
            return  # specifically don't alter the user's selection
        else:
            self._results.setText(f"{len(match_items)} matches")
            self.adjustSize()

        incr = int(math.copysign(min(len(match_items) - 1, abs(incr)), incr))  # clamp to results
        item = match_items[incr]

        self._table.scrollToItem(item)
        self._table.setCurrentItem(item)


class SearchSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds search capability for signals via Ctrl+F."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._find_action = QAction("Find", self)
        self._find_action.setShortcut(QKeyCombination(Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_F))
        self._find_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # require widget focus to fire
        self._find_action.triggered.connect(self._on_find)
        self.addAction(self._find_action)

        self._search_overlay = SearchOverlay(self)
        self._search_overlay.hide()

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._find_action)

    def _on_find(self) -> SearchOverlay:
        self._search_overlay.move(self.mapToGlobal(QPoint(0, 0)))
        self._search_overlay.start()
        self._search_overlay.show()
        self._search_overlay.setFocus()
        return self._search_overlay
