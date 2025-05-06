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

from typing import Dict, List, Any, Mapping, Tuple

import numpy as np
import numpy.typing as npt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QTableWidgetItem, QMenu

from .util import not_none
from .cache_dict import IdentityCacheDict
from .signals_table import ContextMenuSignalsTable


class TimeshiftSignalsTable(ContextMenuSignalsTable):
    """Mixin into SignalsTable that adds a UI to time-shift a signal.
    This acts as the data store and transformer to apply the time-shift, but the actual
    values are set externally (by a function call, typically from the top-level coordinator
    that gets its data from the user dragging a plot line)."""

    COL_TIMESHIFT = -1

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._set_timeshift_action = QAction("Set Timeshift", self)
        self._set_timeshift_action.triggered.connect(self._on_set_timeshift)
        self.cellDoubleClicked.connect(self._on_timeshift_double_click)

        self._timeshifts: Dict[str, float] = {}  # data name -> time delay
        self._cached_results = IdentityCacheDict[
            npt.NDArray[np.float64], npt.NDArray[np.float64]
        ]()  # src x-values -> output x-values

    def _post_cols(self) -> int:
        self.COL_TIMESHIFT = super()._post_cols()
        return self.COL_TIMESHIFT + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_TIMESHIFT, QTableWidgetItem("Timeshift"))

    def set_data_items(self, new_data_items: List[Tuple[str, QColor]]) -> None:
        super().set_data_items(new_data_items)
        for row, (name, color) in enumerate(self._data_items.items()):
            timeshift = self._timeshifts.get(name)
            if timeshift is not None:
                not_none(self.item(row, self.COL_TIMESHIFT)).setText(str(timeshift))
            else:
                not_none(self.item(row, self.COL_TIMESHIFT)).setText("")

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._set_timeshift_action)

    def _on_timeshift_double_click(self, row: int, col: int) -> None:
        if col == self.COL_TIMESHIFT:
            self._on_set_timeshift()

    def _on_set_timeshift(self) -> None:
        data_names = list(self._data_items.keys())
        selected_data_names = [data_names[item.row()] for item in self.selectedItems()]
        if len(selected_data_names) == 0:
            return
        if selected_data_names[0] in self._timeshifts:
            initial_timeshift = self._timeshifts[selected_data_names[0]]
        else:
            initial_timeshift = 0
        self.sigTimeshiftHandle.emit(selected_data_names, initial_timeshift)

    def set_timeshift(self, data_names: List[str], timeshift: float) -> None:
        """Called externally (eg, by handle drag) to set the timeshift for the specified data names."""
        index_by_data_name = {data_name: i for i, data_name in enumerate(self._data_items.keys())}
        for data_name in data_names:
            self._timeshifts[data_name] = timeshift
            not_none(self.item(index_by_data_name[data_name], self.COL_TIMESHIFT)).setText(str(timeshift))
        self.sigTimeshiftChanged.emit(data_names)

    def apply_timeshifts(
        self,
        data_name: str,
        all_data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> npt.NDArray[np.float64]:
        """Applies timeshifts to the specified data_name and data. Returns the transformed X values (time values, data is not used),
        which may be the input data if no timeshift is specified.
        Returns identical objects for identical inputs and consecutive identical timeshifts (results are cached).
        """
        xs = all_data[data_name][0]
        timeshift = self._timeshifts.get(data_name, 0)
        if timeshift == 0:  # no timeshift applied
            return xs
        cached_result = self._cached_results.get(xs, timeshift, [], None)
        if cached_result is not None:
            return cached_result
        result = np.add(xs, timeshift)
        self._cached_results.set(xs, timeshift, [], result)
        return result
