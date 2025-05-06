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
from typing import Dict, Tuple, List, Any, Mapping, Union, Optional, TextIO

import numpy as np
import numpy.typing as npt
from PySide6.QtGui import QColor, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSplitter, QFileDialog

from .multi_plot_widget import (
    MultiPlotWidget,
    DroppableMultiPlotWidget,
    LinkedMultiPlotWidget,
)
from .signals_table import StatsSignalsTable, DraggableSignalsTable
from .transforms_signal_table import TransformsSignalsTable


class PlotsTableWidget(QSplitter):
    class PlotsTableMultiPlots(DroppableMultiPlotWidget, LinkedMultiPlotWidget):
        """MultiPlotWidget used in PlotsTableWidget with required mixins."""

    class PlotsTableSignalsTable(DraggableSignalsTable, TransformsSignalsTable, StatsSignalsTable):
        """SignalsTable used in PlotsTableWidget with required mixins."""

        def __init__(self, plots: MultiPlotWidget, *args: Any, **kwargs: Any) -> None:
            self._plots = plots
            super().__init__(*args, **kwargs)

        def _render_value(self, data_name: str, value: float) -> str:
            return self._plots.render_value(data_name, value)

    def _make_plots(self) -> PlotsTableMultiPlots:
        """Returns the plots widget. Optionally override to use a different plots widget."""
        return self.PlotsTableMultiPlots()

    def _make_table(self) -> PlotsTableSignalsTable:
        """Returns the signals table widget. Optionally override to use a different signals widget.
        Plots are created first, and this may reference plots."""
        return self.PlotsTableSignalsTable(self._plots)

    def _make_controls(self) -> QWidget:
        """Returns the control panel widget. Optional, defaults to nothing."""
        return QWidget()

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._controls = self._make_controls()
        self._plots = self._make_plots()
        self._table = self._make_table()

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self._table)
        bottom_layout.addWidget(self._controls)
        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_layout)
        self.setOrientation(Qt.Orientation.Vertical)
        self.addWidget(self._plots)
        self.addWidget(bottom_widget)

        self._data_items: Dict[str, Tuple[QColor, "MultiPlotWidget.PlotType"]] = {}
        self._transformed_data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}
        self._data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}

        self._plots.sigCursorRangeChanged.connect(self._on_region_change)
        self._table.sigTransformChanged.connect(self._on_transform_change)

    def _set_data_items(
        self,
        new_data_items: List[Tuple[str, QColor, "MultiPlotWidget.PlotType"]],
    ) -> None:
        self._data_items = {name: (color, plot_type) for name, color, plot_type in new_data_items}
        self._plots.show_data_items(new_data_items, no_create=len(new_data_items) > 8)
        self._table.set_data_items([(data_name, color) for data_name, color, _ in new_data_items])

    def _to_array(self, x: npt.ArrayLike) -> npt.NDArray[np.float64]:
        if isinstance(x, np.ndarray) and x.flags.writeable == False:
            return x
        else:
            arr = np.array(x)
            arr.flags.writeable = False
            return arr

    def _transform_data(
        self,
        data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]]:
        transformed_data = {}
        for data_name in data.keys():
            transformed = self._table.apply_transform(data_name, data)
            if isinstance(transformed, Exception):
                pass
            else:
                transformed_data[data_name] = data[data_name][0], transformed
        return transformed_data

    def _set_data(
        self,
        data: Mapping[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]],
    ) -> None:
        self._data = {data_name: (self._to_array(xs), self._to_array(ys)) for data_name, (xs, ys) in data.items()}
        self._transformed_data = self._transform_data(self._data)
        self._plots.set_data(self._transformed_data)
        self._table.set_data(
            {
                data_name: vals
                for data_name, vals in self._transformed_data.items()
                if self._data_items.get(data_name, (None, MultiPlotWidget.PlotType.DEFAULT))[1]
                != MultiPlotWidget.PlotType.ENUM_WAVEFORM
            }
        )

    def _on_region_change(self, region: Optional[Union[float, Tuple[float, float]]]) -> None:
        if isinstance(region, tuple):
            self._table.set_range(region)
        else:
            self._table.set_range((-float("inf"), float("inf")))

    def _on_transform_change(self, data_names: List[str]) -> None:
        self._set_data(self._data)  # TODO minimal changes in the future

    def _write_csv(self, fileio: Union[TextIO, StringIO]) -> None:
        writer = csv.writer(fileio)
        writer.writerow(["# time"] + [name for name, _ in self._data.items()])

        indices = [0] * len(self._data.items())  # indices to examine on current iteration, in self._data order
        ordered_data_items = list(self._data.values())
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
        if self._data is None:
            return
        filename, filter = QFileDialog.getSaveFileName(self, f"Save Data", "", "CSV (*.csv)")
        if not filename:
            return

        with open(filename, "w", newline="") as f:
            self._write_csv(f)
