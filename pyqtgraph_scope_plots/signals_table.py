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
import math
import queue
import weakref
from typing import Dict, Tuple, List, Any, Mapping, Optional, NamedTuple

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QMimeData, QPoint, Signal, QObject, QThread
from PySide6.QtGui import QColor, Qt, QAction, QDrag, QPixmap, QMouseEvent
from PySide6.QtWidgets import QTableWidgetItem, QTableWidget, QHeaderView, QMenu, QLabel, QColorDialog
from pydantic import BaseModel

from .cache_dict import IdentityCacheDict
from .multi_plot_widget import MultiPlotWidget, LinkedMultiPlotWidget
from .save_restore_model import BaseTopModel, DataTopModel, HasSaveLoadDataConfig
from .util import not_none


class SignalsTable(QTableWidget):
    """Table of signals. Includes infrastructure to allow additional mixed-in classes to extend the table columns."""

    COL_NAME: int = -1  # dynamically init'd
    COL_COUNT: int = 0

    sigDataDeleted = Signal(
        list, list
    )  # list[int] rows, list[str] strings TODO: signals don't play well with multiple inheritance
    sigColorChanged = Signal(object)  # List[(str, QColor)] of color changed
    sigTransformChanged = Signal(object)  # List[str] of data names of changed transforms
    sigTimeshiftHandle = Signal(object, float)  # List[str] of data names, initial (prior) timeshift
    sigTimeshiftChanged = Signal(object)  # List[str] of data names

    @classmethod
    def _create_noneditable_table_item(cls, *args: Any) -> QTableWidgetItem:
        """Creates a non-editable QTableWidgetItem (table cell)"""
        item = QTableWidgetItem(*args)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # make non-editable
        return item

    def _pre_cols(self) -> int:  # number of cols before nane
        """Called during beginning of __init__ to calculate column counts.
        Subclasses should override this (with an accumulating super() call) and initialize their offsets.
        """
        return 0

    def _post_cols(self) -> int:  # total number of columns, including _pre_cols
        """Called during beginning of __init__ to calculate column counts.
        Subclasses should override this (with an accumulating super() call) and initialize their offsets.
        """
        return self.COL_NAME + 1  # 1 for the name column

    def _init_col_counts(self) -> None:
        """Called during beginning of init to initialize column offsets and counts. Do NOT override."""
        if self.COL_NAME == -1 or self.COL_COUNT == 0:
            self.COL_NAME = self._pre_cols()
            self.COL_COUNT = self._post_cols()

    def _init_table(self) -> None:
        """Called during init, AFTER _init_col_counts (and where offsets and counts should be valid), to
        do any table initialization like setting up headers.
        Subclasses should override this (including a super() call)"""
        self.setHorizontalHeaderItem(self.COL_NAME, QTableWidgetItem("Name"))

    def __init__(self, plots: MultiPlotWidget) -> None:
        super().__init__()
        self._plots = plots
        self._init_col_counts()
        self.setColumnCount(self.COL_COUNT)
        self._init_table()

        header = self.horizontalHeader()
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        self._data_items: Dict[str, QColor] = {}

    def set_data_items(self, new_data_items: List[Tuple[str, QColor]]) -> None:
        self._data_items = {data_name: color for data_name, color in new_data_items}

        self.setRowCount(0)  # clear the existing table, other resizing becomes really expensive
        self.setRowCount(len(self._data_items))  # create new items
        for row, (name, color) in enumerate(self._data_items.items()):
            for col in range(self.COL_COUNT):
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

        region = (region[0] - region[0] * ROUNDING_FACTOR, region[1] + region[1] * ROUNDING_FACTOR)
        low_index = bisect.bisect_left(ts, region[0])  # inclusive
        high_index = bisect.bisect_right(ts, region[1])  # exclusive
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

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._delete_row_action = QAction("Remove", self)
        self._delete_row_action.setShortcut(Qt.Key.Key_Delete)
        self._delete_row_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # require widget focus to fire
        self._delete_row_action.triggered.connect(self._on_data_items_delete)
        self.addAction(self._delete_row_action)

    def _on_data_items_delete(self) -> None:
        """Called when data items are deleted, to actually execute the deletion. Optional if supported."""
        data_names = list(self._data_items.keys())
        rows = list(set([item.row() for item in self.selectedItems()]))
        self.sigDataDeleted.emit(rows, [data_names[row] for row in rows])

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._delete_row_action)


class ColorPickerDataStateModel(DataTopModel):
    color: Optional[str] = None  # QColor name, e.g., '#ffea70' or 'red'


class ColorPickerSignalsTable(ContextMenuSignalsTable, HasSaveLoadDataConfig):
    """Mixin into SignalsTable that adds a context menu item for the user to change the color.
    This gets sent as a signal, and an upper must handle plumbing the colors through.
    """

    _DATA_MODEL_BASES = [ColorPickerDataStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._colors: Dict[str, QColor] = {}  # only for save state
        self._set_color_action = QAction("Set Color", self)
        self._set_color_action.triggered.connect(self._on_set_color)

    def _write_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._write_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, ColorPickerDataStateModel)
            color = self._colors.get(data_name, None)
            if color is not None:
                data_model.color = color.name()

    def _load_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._load_model(model)
        data_name_colors = []
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, ColorPickerDataStateModel)
            if data_model.color is not None:
                data_name_colors.append((data_name, QColor(data_model.color)))
        self.sigColorChanged.emit(data_name_colors)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._set_color_action)

    def _on_set_color(self) -> None:
        data_names = list(self._data_items.keys())
        selected_data_names = [data_names[item.row()] for item in self.selectedItems()]
        color = QColorDialog.getColor()
        for data_name in selected_data_names:
            self._colors[data_name] = color
        self.sigColorChanged.emit([(data_name, color) for data_name in selected_data_names])


class DraggableSignalsTable(SignalsTable):
    """Mixin into SignalsTable that allows rows to be dragged and dropped into a DroppableMultiPlotWidget.
    Rows are presented in selection order."""

    DRAG_MIME_TYPE = "application/x.plots.dataname"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._ordered_selects: List[QTableWidgetItem] = []
        self.itemSelectionChanged.connect(self._on_select_changed)

    def _on_select_changed(self) -> None:
        # since selectedItems is not ordered by selection, keep an internal order by tracking changes
        new_selects = [item for item in self.selectedItems() if item not in self._ordered_selects]
        self._ordered_selects = [item for item in self._ordered_selects if item in self.selectedItems()]
        self._ordered_selects.extend(new_selects)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if e.buttons() == Qt.MouseButton.LeftButton:
            if not self._ordered_selects:
                return
            data_names = list(self._data_items.keys())
            item_names = [data_names[item.row()] for item in self._ordered_selects]

            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(self.DRAG_MIME_TYPE, "\0".join(item_names).encode("utf-8"))
            drag.setMimeData(mime)

            drag_label = QLabel(", ".join(item_names))
            pixmap = QPixmap(drag_label.size())
            drag_label.render(pixmap)
            drag.setPixmap(pixmap)

            drag.exec(Qt.DropAction.MoveAction)
