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

import bisect
from typing import Dict, Tuple, List, Any, Optional

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QMimeData, QPoint, Signal
from PySide6.QtGui import QColor, Qt, QAction, QDrag, QPixmap, QMouseEvent
from PySide6.QtWidgets import QTableWidgetItem, QHeaderView, QMenu, QLabel

from .multi_plot_widget import MultiPlotWidget, LinkedMultiPlotWidget
from .util import MixinColsTable, not_none


class SignalsTable(MixinColsTable):
    """Table of signals. Includes infrastructure to allow additional mixed-in classes to extend the table columns."""

    COL_NAME: int = -1  # dynamically init'd

    @classmethod
    def _create_noneditable_table_item(cls, *args: Any) -> QTableWidgetItem:
        """Creates a non-editable QTableWidgetItem (table cell)"""
        item = QTableWidgetItem(*args)
        item.setFlags(
            item.flags() & ~Qt.ItemFlag.ItemIsEditable & ~Qt.ItemFlag.ItemIsUserCheckable
        )  # make non-editable
        return item

    def _post_cols(self) -> int:  # total number of columns, including _pre_cols
        self.COL_NAME = super()._post_cols()
        return self.COL_NAME + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_NAME, QTableWidgetItem("Name"))

    def __init__(self, plots: MultiPlotWidget) -> None:
        super().__init__()
        self._plots = plots

        header = self.horizontalHeader()
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        self._data_items: Dict[str, QColor] = {}

        self._plots.sigDataItemsUpdated.connect(self._update)

    def _update(self) -> None:
        self._data_items = {data_name: color for data_name, (color, _) in self._plots._data_items.items()}

        self.setRowCount(0)  # clear the existing table, other resizing becomes really expensive
        self.setRowCount(len(self._data_items))  # create new items
        for row, (name, color) in enumerate(self._data_items.items()):
            for col in range(self.columnCount()):
                item = self._create_noneditable_table_item()
                item.setForeground(color)
                self.setItem(row, col, item)
            not_none(self.item(row, self.COL_NAME)).setText(name)


class HasRegionSignalsTable(SignalsTable):
    """Provides utilities for getting the region from a plot"""

    @staticmethod
    def _region_of_plot(plots: MultiPlotWidget) -> Tuple[float, float]:
        """Returns the region of a plot, if the plot supports regions, otherwise returns (-inf, inf)."""
        if isinstance(plots, LinkedMultiPlotWidget) and isinstance(plots._last_region, tuple):
            return plots._last_region
        else:
            return (-float("inf"), float("inf"))

    @classmethod
    def _indices_of_region(
        cls, ts: npt.NDArray[np.float64], region: Tuple[float, float]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Given sorted ts and a region, return the indices of ts containing the region.
        Expands the region slightly to account for floating point imprecision"""
        ROUNDING_FACTOR = 2e-7

        tolerance = (region[1] - region[0]) * ROUNDING_FACTOR
        low_index = bisect.bisect_left(ts, region[0] - tolerance)  # inclusive
        high_index = bisect.bisect_right(ts, region[1] + tolerance)  # exclusive
        if low_index >= high_index:  # empty set
            return None, None
        else:
            return low_index, high_index


class ContextMenuSignalsTable(SignalsTable):
    """Mixin into SignalsTable that adds a context menu on rows."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._spawn_table_cell_menu)

    def _spawn_table_cell_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        self._populate_context_menu(menu)
        menu.popup(self.mapToGlobal(pos))

    def _populate_context_menu(self, menu: QMenu) -> None:
        """Called when the context menu is created, to populate its items."""
        pass


class DeleteableSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds a hook for item deletion, both as hotkey and from a context menu."""

    sigDataDeleted: Signal
    # Multiple inheritance / mixins interact badly with signals, so the signal must be instantiated elsewhere,
    # probably in the class extending these mixins. Add this line of code:
    # sigDataDeleted = Signal(object, object)  # List[rows], List[data_names]

    _DELETE_ACTION_NAME = "Remove"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._delete_row_action = QAction(self._DELETE_ACTION_NAME, self)
        self._delete_row_action.setShortcut(Qt.Key.Key_Delete)
        self._delete_row_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # require widget focus to fire

        assert hasattr(
            self, "sigDataDeleted"
        ), f"{self.__class__.__name__} must define sigDataDeleted, see documentation in DeleteableSignalsTable"

        def on_delete_rows() -> None:
            rows = list(set([item.row() for item in self.selectedItems()]))
            all_data_names = list(self._data_items.keys())
            data_names = [all_data_names[row] for row in rows]
            self.sigDataDeleted.emit(rows, data_names)

        self._delete_row_action.triggered.connect(on_delete_rows)
        self.addAction(self._delete_row_action)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._delete_row_action)


class DraggableSignalsTable(SignalsTable):
    """Mixin into SignalsTable that allows rows to be dragged and dropped into a DroppableMultiPlotWidget.
    Rows are presented in selection order."""

    DRAG_MIME_TYPE = "application/x.plots.dataname"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._ordered_selects: List[Tuple[int, int]] = []  # row, col
        self.itemSelectionChanged.connect(self._on_select_changed)

    def _on_select_changed(self) -> None:
        # since selectedItems is not ordered by selection, keep an internal order by tracking changes
        selected = [(item.row(), item.column()) for item in self.selectedItems()]
        new_selects = [item for item in selected if item not in self._ordered_selects]
        self._ordered_selects = [item for item in self._ordered_selects if item in selected]
        self._ordered_selects.extend(new_selects)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if e.buttons() == Qt.MouseButton.LeftButton:
            if not self._ordered_selects:
                return
            data_names = list(self._data_items.keys())
            item_names = [data_names[item[0]] for item in self._ordered_selects]

            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(self.DRAG_MIME_TYPE, "\0".join(item_names).encode("utf-8"))
            drag.setMimeData(mime)

            drag_label = QLabel(", ".join(item_names))
            pixmap = QPixmap(drag_label.size())
            drag_label.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec(Qt.DropAction.MoveAction)
