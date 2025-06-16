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

import csv
from io import StringIO
from typing import Tuple, List, Any, Mapping, Union, Optional, TextIO, Type

import numpy as np
import numpy.typing as npt
from PySide6.QtGui import QColor, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QFileDialog

from .multi_plot_widget import (
    MultiPlotWidget,
    DroppableMultiPlotWidget,
    LinkedMultiPlotWidget,
)
from .signals_table import DraggableSignalsTable
from .signals_table import SignalsTable as OriginalSignalsTable


class PlotsTableWidget(QSplitter):
    class Plots(DroppableMultiPlotWidget, LinkedMultiPlotWidget):
        """MultiPlotWidget used in PlotsTableWidget with required mixins."""

    class SignalsTable(DraggableSignalsTable):
        """SignalsTable used in PlotsTableWidget with required mixins."""

    _PLOT_TYPE: Type[MultiPlotWidget] = Plots
    _TABLE_TYPE: Type[OriginalSignalsTable] = SignalsTable

    def _make_plots(self) -> MultiPlotWidget:
        """Returns the plots widget. Optionally override to use a different plots widget."""
        return self._PLOT_TYPE()

    def _make_table(self) -> OriginalSignalsTable:
        """Returns the signals table widget. Optionally override to use a different signals widget.
        Plots are created first, and this may reference plots."""
        return self._TABLE_TYPE(self._plots)

    def _make_controls(self) -> Optional[QWidget]:
        """Returns the control panel widget. Optional, defaults to empty."""
        return None

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._controls = self._make_controls()
        self._plots = self._make_plots()
        self._table = self._make_table()

        self.setOrientation(Qt.Orientation.Vertical)
        self.addWidget(self._plots)
        if self._controls is not None:
            bottom_layout = QHBoxLayout()
            bottom_layout.addWidget(self._table)
            bottom_layout.addWidget(self._controls)
            bottom_widget = QWidget()
            bottom_widget.setLayout(bottom_layout)
            self.addWidget(bottom_widget)
        else:
            self.addWidget(self._table)

    def _set_data_items(
        self,
        new_data_items: List[Tuple[str, QColor, "MultiPlotWidget.PlotType"]],
    ) -> None:
        self._plots.show_data_items(new_data_items, no_create=len(new_data_items) > 8)

    def _set_data(
        self,
        data: Mapping[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]],
    ) -> None:
        self._plots.set_data(data)

    def _write_csv(self, fileio: Union[TextIO, StringIO]) -> None:
        writer = csv.writer(fileio)
        writer.writerow(["# time"] + [name for name, _ in self._plots._data.items()])

        indices = [0] * len(self._plots._data.items())  # indices to examine on current iteration, in self._data order
        ordered_data_items = list(self._plots._data.values())
        while True:  # iterate each row
            xs_at_index = [
                ordered_data_items[data_index][0][point_index]
                for data_index, point_index in enumerate(indices)
                if point_index < len(ordered_data_items[data_index][0])
            ]
            if not len(xs_at_index):  # indices overran all lists, we're done
                break
            min_x = min(xs_at_index)
            this_row = [str(min_x)]
            for i, (xs, ys) in enumerate(ordered_data_items):
                if indices[i] < len(xs) and xs[indices[i]] == min_x:
                    this_row.append(str(ys[indices[i]]))
                    indices[i] += 1
                else:
                    this_row.append("")

            writer.writerow(this_row)

    def _save_csv_dialog(self) -> None:
        """Utility function to open a dialog to export the current data to a CSV with a shared x-axis column."""
        filename, filter = QFileDialog.getSaveFileName(self, f"Save Data", "", "CSV (*.csv)")
        if not filename:
            return

        with open(filename, "w", newline="") as f:
            self._write_csv(f)
