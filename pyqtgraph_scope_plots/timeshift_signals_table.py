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
from typing import Dict, List, Any, Mapping, Tuple, Optional

import numpy as np
import numpy.typing as npt
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QAction, Qt, QDoubleValidator
from PySide6.QtWidgets import QTableWidgetItem, QMenu, QStyledItemDelegate, QLineEdit, QWidget
from pydantic import BaseModel

from .multi_plot_widget import LinkedMultiPlotWidget
from .signals_table import ContextMenuSignalsTable
from .util import IdentityCacheDict, DataTopModel, HasSaveLoadDataConfig, BaseTopModel, not_none


class TimeshiftDataStateModel(DataTopModel):
    timeshift: Optional[float] = None


class TimeshiftPlotWidget(LinkedMultiPlotWidget, HasSaveLoadDataConfig):
    """MultiPlotWidget that adds a user-defined data transform."""

    _DATA_MODEL_BASES = [TimeshiftDataStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        self._timeshifts: Dict[str, float] = {}  # data name -> time delay
        self._timeshifts_cached_results = IdentityCacheDict[
            npt.NDArray[np.float64], npt.NDArray[np.float64]
        ]()  # src x-values -> output x-values

        super().__init__(*args, **kwargs)

        # state variables for timeshift drag handle
        self._timeshifts_drag_data_items: List[str] = []
        self._timeshifts_drag_offset: float = 0
        self.sigDragCursorChanged.connect(self._on_timeshift_drag)
        self.sigDragCursorCleared.connect(self._on_timeshift_drag_clear)

    def _write_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._write_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, TimeshiftDataStateModel)
            timeshift = self._timeshifts.get(data_name, 0)
            data_model.timeshift = timeshift

    def _load_model(self, model: BaseModel) -> None:
        assert isinstance(model, BaseTopModel)
        super()._load_model(model)
        for data_name, data_model in model.data.items():
            assert isinstance(data_model, TimeshiftDataStateModel)
            if data_model.timeshift is not None:
                self.set_timeshift([data_name], data_model.timeshift, update=False)

    def set_timeshift(self, data_names: List[str], timeshift: float, update: bool = True) -> None:
        """Called externally (eg, by handle drag) to set the timeshift for the specified data names.
        Optionally, updating can be disabled for performance, for example to batch-update after a bunch of ops."""
        for data_name in data_names:
            self._timeshifts[data_name] = timeshift
        if update:
            self._update_plots()
            self.sigDataUpdated.emit()

    def _apply_timeshift(
        self, data_name: str, all_data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]]
    ) -> npt.NDArray[np.float64]:
        """Applies timeshift on the specified data_name and returns the x points."""
        xs, _ = all_data[data_name]
        timeshift = self._timeshifts.get(data_name, 0)
        if timeshift == 0:  # no timeshift applied
            return xs
        result = self._timeshifts_cached_results.get(xs, timeshift, [], None)
        if result is None:
            result = np.add(xs, timeshift)
            self._timeshifts_cached_results.set(xs, timeshift, [], result)
        return result

    def _transform_data(
        self, data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]]
    ) -> Mapping[str, Tuple[npt.NDArray, npt.NDArray]]:
        """Applies timeshifts to the specified data_name and data. Returns the transformed X values (time values, data is not used),
        which may be the input data if no timeshift is specified.
        Returns identical objects for identical inputs and consecutive identical timeshifts (results are cached).
        """
        data = super()._transform_data(data)
        transformed_data = {}
        for data_name in data.keys():
            xs, ys = data[data_name]
            transformed_data[data_name] = (self._apply_timeshift(data_name, data), ys)
        return transformed_data

    def start_timeshift_drag(self, data_names: List[str]) -> None:
        """Creates a timeshift drag handle to allow the user to visually drag a timeshift"""
        if not data_names:
            return

        # try to find a drag point that is near the center of the view window, and preferably at a data point
        view_left, view_right = self.view_x_range()
        view_center = (view_left + view_right) / 2
        data_x, data_y = self._data.get(data_names[0], (np.array([]), np.array([])))
        index = bisect.bisect_left(data_x, view_center)
        if index >= len(data_x):  # snap to closest point
            index = len(data_x) - 1
        elif index < 0:
            index = 0
        if len(data_x) and data_x[index] >= view_left and data_x[index] <= view_right:  # point in view
            handle_pos = float(data_x[index])  # cast from numpy float
        else:  # no points in view
            handle_pos = view_center

        self._timeshifts_drag_data_items = data_names
        self._timeshifts_drag_offset = handle_pos - self._timeshifts.get(data_names[0], 0)
        self.create_drag_cursor(handle_pos)

    def _on_timeshift_drag(self, pos: float) -> None:
        self.set_timeshift(self._timeshifts_drag_data_items, pos - self._timeshifts_drag_offset)

    def _on_timeshift_drag_clear(self) -> None:
        self._timeshifts_drag_data_items = []


class FloatValidatorDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option: Any, index: Any) -> QLineEdit:
        editor = QLineEdit(parent)
        editor.setValidator(QDoubleValidator(parent))
        return editor


class TimeshiftSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds a UI to time-shift a signal.
    This acts as the data store and transformer to apply the time-shift, but the actual
    values are set externally (by a function call, typically from the top-level coordinator
    that gets its data from the user dragging a plot line)."""

    COL_TIMESHIFT = -1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._drag_timeshift_action = QAction("Drag Timeshift", self)
        self._drag_timeshift_action.triggered.connect(self._on_drag_timeshift)
        self._plots.sigDataUpdated.connect(self._update_timeshifts)
        self._update_timeshifts()
        self.cellChanged.connect(self._on_timeshift_cell)

    def _post_cols(self) -> int:
        self.COL_TIMESHIFT = super()._post_cols()
        return self.COL_TIMESHIFT + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_TIMESHIFT, QTableWidgetItem("Timeshift"))
        self.setItemDelegateForColumn(self.COL_TIMESHIFT, FloatValidatorDelegate(self))

    def _update(self) -> None:
        with QSignalBlocker(self):  # prevent self update from triggering timeshift edited
            super()._update()  # including when the table items are created
            for row in range(self.rowCount()):
                item = self.item(row, self.COL_TIMESHIFT)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)

    def _update_timeshifts(self) -> None:
        assert isinstance(self._plots, TimeshiftPlotWidget)
        with QSignalBlocker(self):  # prevent self update from triggering timeshift edited
            for row, (name, color) in enumerate(self._data_items.items()):
                timeshift = self._plots._timeshifts.get(name)
                item = not_none(self.item(row, self.COL_TIMESHIFT))
                if timeshift is not None and timeshift != 0:
                    item.setText(str(timeshift))
                else:
                    item.setText("")

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._drag_timeshift_action)

    def _on_timeshift_cell(self, row: int, col: int) -> None:
        if col != self.COL_TIMESHIFT:
            return
        assert isinstance(self._plots, TimeshiftPlotWidget)
        data_names = list(self._data_items.keys())
        text = self.item(row, col).text()
        if text == "":
            timeshift = 0.0
        else:
            try:
                timeshift = float(text)
            except ValueError:
                self._update_timeshifts()  # reassign to actual value
                return
        self._plots.set_timeshift([data_names[row]], timeshift)

    def _on_drag_timeshift(self) -> None:
        assert isinstance(self._plots, TimeshiftPlotWidget)
        data_names = list(self._data_items.keys())
        selected_data_names = [data_names[item.row()] for item in self.selectedItems()]
        self._plots.start_timeshift_drag(selected_data_names)
