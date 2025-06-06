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

from .cache_dict import IdentityCacheDict
from .save_restore_model import HasSaveLoadConfig, DataTopModel, BaseTopModel
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
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
    """A SignalsTable that listens for a region change and provides some utilities"""

    def set_range(self, range: Tuple[float, float]) -> None:
        self._range = range

    @classmethod
    def _indices_of_region(
        cls, xs: npt.NDArray[np.float64], region: Tuple[float, float]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Given the x points and a region, return the indices of xs containing the region"""
        low_index = bisect.bisect_left(xs, region[0])  # inclusive
        high_index = bisect.bisect_right(xs, region[1])  # exclusive
        if low_index >= high_index:  # empty set
            return None, None
        else:
            return low_index, high_index


class HasDataSignalsTable(SignalsTable):
    """A SignalsTable that stores a copy of the data"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}

    def set_data(
        self,
        data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> None:
        self._data = data


class StatsSignalsTable(HasRegionSignalsTable, HasDataSignalsTable):
    """Mixin into SignalsTable with statistics rows. Optional range to specify computation of statistics.
    Values passed into set_data must all be numeric."""

    COL_STAT = -1
    COL_STAT_MIN = 0  # offset from COL_STAT
    COL_STAT_MAX = 1
    COL_STAT_AVG = 2
    COL_STAT_RMS = 3
    COL_STAT_STDEV = 4
    STATS_COLS = [
        COL_STAT_MIN,
        COL_STAT_MAX,
        COL_STAT_AVG,
        COL_STAT_RMS,
        COL_STAT_STDEV,
    ]

    FULL_RANGE = (-float("inf"), float("inf"))

    class StatsCalculatorSignals(QObject):
        update = Signal(object, object, object)  # input array, region, {stat (by offset col) -> value}

    class StatsCalculatorThread(QThread):
        """Stats calculated in a separate thread to avoid blocking the main GUI thread when large regions
        are selected.
        This thread is persistent and monitors its queue for requests to work. Requests (near)immediately
        override whatever previous computation was in progress and are not queued.
        Thread sleeps when current task and queue is empty."""

        class Task(NamedTuple):
            """A request for computing statistics of some ys and region (over xs, inclusive).
            data is stored as a weakref to terminate computation early if data goes out of scope"""

            data: List[Tuple[weakref.ref[npt.NDArray[np.float64]], weakref.ref[npt.NDArray[np.float64]]]]
            region: Tuple[float, float]

        def __init__(self, parent: Any):
            super().__init__(parent)
            self.signals = StatsSignalsTable.StatsCalculatorSignals()
            self.queue: queue.Queue[StatsSignalsTable.StatsCalculatorThread.Task] = queue.Queue()

        def run(self) -> None:
            while True:
                task = self.queue.get()  # get at least one task, blocking
                while not self.queue.empty():  # but get the latest, if multiple, discarding earlier
                    task = self.queue.get()

                for xs_ys_ref in task.data:
                    if not self.queue.empty():  # new task, drop current task
                        break

                    xs = xs_ys_ref[0]()
                    ys = xs_ys_ref[1]()
                    if xs is None or ys is None:  # skip objects that have been deleted
                        continue
                    low_index, high_index = HasRegionSignalsTable._indices_of_region(xs, task.region)
                    if low_index is None or high_index is None:  # empty set
                        ys_region = np.array([])
                    else:
                        ys_region = ys[low_index:high_index]
                    stats_dict = self._calculate_stats(ys_region)
                    self.signals.update.emit(ys, task.region, stats_dict)

        def terminate_wait(self) -> None:
            self.terminate()
            self.wait()  # needed otherwise pytest fails on Linux

        @classmethod
        def _calculate_stats(cls, ys: npt.NDArray[np.float64]) -> Dict[int, float]:
            """Calculates stats (as dict of col offset -> value) for the specified xs, ys.
            Does not spawn a separate thread, does not affect global state."""
            if len(ys) == 0:
                return {}
            stats_dict = {}
            mean = sum(ys) / len(ys)
            stats_dict[StatsSignalsTable.COL_STAT_MIN] = min(ys)
            stats_dict[StatsSignalsTable.COL_STAT_MAX] = max(ys)
            stats_dict[StatsSignalsTable.COL_STAT_AVG] = mean
            stats_dict[StatsSignalsTable.COL_STAT_RMS] = math.sqrt(sum([x**2 for x in ys]) / len(ys))
            stats_dict[StatsSignalsTable.COL_STAT_STDEV] = math.sqrt(sum([(x - mean) ** 2 for x in ys]) / len(ys))
            return stats_dict

    def _post_cols(self) -> int:
        self.COL_STAT = super()._post_cols()
        return self.COL_STAT + 5

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_MIN, QTableWidgetItem("Min"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_MAX, QTableWidgetItem("Max"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_AVG, QTableWidgetItem("Avg"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_RMS, QTableWidgetItem("RMS"))
        self.setHorizontalHeaderItem(self.COL_STAT + self.COL_STAT_STDEV, QTableWidgetItem("StDev"))

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # since calculating stats across the full range is VERY EXPENSIVE, cache the results
        self._full_range_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict
        self._region_stats = IdentityCacheDict[npt.NDArray[np.float64], Dict[int, float]]()  # array -> stats dict
        self._range: Tuple[float, float] = self.FULL_RANGE

        self._stats_compute_thread = self.StatsCalculatorThread(self)
        self._stats_compute_thread.signals.update.connect(self._on_stats_updated)
        self._stats_compute_thread.start(QThread.Priority.IdlePriority)
        self.destroyed.connect(lambda: self._stats_compute_thread.terminate_wait())

    def _on_stats_updated(
        self, input_arr: npt.NDArray[np.float64], region: Tuple[float, float], stats_dict: Dict[int, float]
    ) -> None:
        if region == self.FULL_RANGE:
            self._full_range_stats.set(input_arr, None, [], stats_dict)
        elif region == self._range:
            self._region_stats.set(input_arr, region, [], stats_dict)

        if region == self._range:  # update display as needed
            self._update_stats()

    def set_data(
        self,
        data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> None:
        """Sets the data and updates statistics"""
        super().set_data(data)
        self._create_stats_task()
        self._update_stats()

    def set_range(self, range: Tuple[float, float]) -> None:
        super().set_range(range)
        self._create_stats_task()
        self._update_stats()

    def _create_stats_task(self) -> None:
        if self._range == self.FULL_RANGE:  # for full range, deduplicate with cache
            needed_stats = [
                (weakref.ref(xs), weakref.ref(ys))
                for name, (xs, ys) in self._data.items()
                if self._full_range_stats.get(ys, None, []) is None
            ]
        else:
            needed_stats = [(weakref.ref(xs), weakref.ref(ys)) for name, (xs, ys) in self._data.items()]
        self._stats_compute_thread.queue.put(self.StatsCalculatorThread.Task(needed_stats, self._range))

    def _render_value(self, data_name: str, value: float) -> str:
        """Float-to-string conversion for a value. Optionally override this to provide smarter precision."""
        return f"{value:.3f}"

    def _update_stats(self) -> None:
        for row, name in enumerate(self._data_items.keys()):
            xs, ys = self._data.get(name, (None, None))
            if xs is None or ys is None:
                for col in self.STATS_COLS:
                    not_none(self.item(row, self.COL_STAT + col)).setText("")
                continue

            if self._range == self.FULL_RANGE:  # fetch from cache if available
                stats_dict: Dict[int, float] = self._full_range_stats.get(ys, None, [], {})
            else:  # slice
                stats_dict = self._region_stats.get(ys, self._range, [], {})

            for col_offset in self.STATS_COLS:
                if col_offset in stats_dict:
                    text_value = self._render_value(name, stats_dict[col_offset])
                else:
                    text_value = ""
                not_none(self.item(row, self.COL_STAT + col_offset)).setText(text_value)


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
    color: Optional[str] = None  # QColor name, including hex formats


class ColorPickerSignalsTable(ContextMenuSignalsTable, HasSaveLoadConfig):
    """Mixin into SignalsTable that adds a context menu item for the user to change the color.
    This gets sent as a signal, and an upper must handle plumbing the colors through.
    """

    DATA_MODEL_BASES = [ColorPickerDataStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._colors: Dict[str, QColor] = {}  # only for save state
        self._set_color_action = QAction("Set Color", self)
        self._set_color_action.triggered.connect(self._on_set_color)

    def _write_model(self, model: BaseTopModel) -> None:
        super()._write_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, ColorPickerDataStateModel)
            color = self._colors.get(data_name, None)
            if color is not None:
                data_model.color = color.name()

    def _load_model(self, model: BaseTopModel) -> None:
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
