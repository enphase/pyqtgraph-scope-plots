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
from typing import Dict, Tuple, Any, List, Mapping, Optional, Callable, Sequence, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyqtgraph as pg
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QWidget,
    QPushButton,
    QFileDialog,
    QMenu,
    QCheckBox,
    QVBoxLayout,
)

from ..time_axis import TimeAxisItem
from ..multi_plot_widget import MultiPlotWidget
from ..plots_table_widget import PlotsTableWidget
from ..signals_table import ColorPickerSignalsTable, StatsSignalsTable
from ..timeshift_signals_table import TimeshiftSignalsTable
from ..transforms_signal_table import TransformsSignalsTable
from ..util import int_color


class CsvLoaderPlotsTableWidget(PlotsTableWidget):
    """Example app-level widget that loads CSV files into the plotter"""

    class Plots(PlotsTableWidget.PlotsTableMultiPlots):
        """Adds legend add functionality"""

        def __init__(self, outer: "CsvLoaderPlotsTableWidget", **kwargs: Any) -> None:
            self._outer = outer
            super().__init__(**kwargs)

        def _init_plot_item(self, plot_item: pg.PlotItem) -> pg.PlotItem:
            """Called after _create_plot_item, does any post-creation init. Returns the same plot_item.
            Optionally override this with a super() call."""
            plot_item = super()._init_plot_item(plot_item)
            if self._outer._legend_checkbox.isChecked():
                plot_item.addLegend()
            return plot_item

    class CsvSignalsTable(
        ColorPickerSignalsTable,
        PlotsTableWidget.PlotsTableSignalsTable,
        TransformsSignalsTable,
        TimeshiftSignalsTable,
        StatsSignalsTable,
    ):
        """Adds a hook for item hide"""

        def __init__(self, *args: Any, **kwargs: Any):
            super().__init__(*args, **kwargs)
            self._remove_row_action = QAction("Remove from Plot", self)
            self._remove_row_action.triggered.connect(self._on_rows_remove)

        def _on_rows_remove(self) -> None:
            rows = list(set([item.row() for item in self.selectedItems()]))
            ordered_names = list(self._data_items.keys())
            data_names = [ordered_names[row] for row in rows]
            self._plots.remove_plot_items(data_names)

        def _populate_context_menu(self, menu: QMenu) -> None:
            super()._populate_context_menu(menu)
            menu.addAction(self._remove_row_action)

    def _make_plots(self) -> "CsvLoaderPlotsTableWidget.Plots":
        return self.Plots(self, x_axis=self._x_axis)

    def _make_table(self) -> "CsvLoaderPlotsTableWidget.CsvSignalsTable":
        return self.CsvSignalsTable(self._plots)

    def __init__(self, x_axis: Optional[Callable[[], pg.AxisItem]] = None) -> None:
        self._x_axis = x_axis
        super().__init__()

        self._table: CsvLoaderPlotsTableWidget.CsvSignalsTable
        self._table.sigColorChanged.connect(self._on_color_changed)
        self._drag_handle_data: List[str] = []
        self._drag_handle_offset = 0.0
        self._table.sigTimeshiftHandle.connect(self._on_timeshift_handle)
        self._table.sigTimeshiftChanged.connect(self._on_timeshift_change)
        self._plots.sigDragCursorChanged.connect(self._on_drag_cursor_drag)

    def _transform_data(
        self,
        data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]]:
        # apply time-shift before function transform
        transformed_data = {}
        for data_name in data.keys():
            transformed = self._table.apply_timeshifts(data_name, data)
            transformed_data[data_name] = transformed, data[data_name][1]
        return super()._transform_data(transformed_data)

    def _on_color_changed(self, items: List[Tuple[str, QColor]]) -> None:
        updated_data_items = self._data_items.copy()
        for name, new_color in items:
            if name in updated_data_items:
                updated_data_items[name] = (
                    new_color,
                    self._data_items[name][1],
                )
        self._set_data_items([(name, color, plot_type) for name, (color, plot_type) in updated_data_items.items()])
        self._set_data(self._data)

    def _on_timeshift_handle(self, data_names: List[str], initial_timeshift: float) -> None:
        if not data_names:
            return

        # try to find a drag point that is near the center of the view window, and preferably at a data point
        view_left, view_right = self._plots.view_x_range()
        view_center = (view_left + view_right) / 2
        data_x, data_y = self._transformed_data.get(data_names[0], (np.array([]), np.array([])))
        index = bisect.bisect_left(data_x, view_center)
        if index >= len(data_x):  # snap to closest point
            index = len(data_x) - 1
        elif index < 0:
            index = 0
        if len(data_x) and data_x[index] >= view_left and data_x[index] <= view_right:  # point in view
            handle_pos: float = data_x[index]
        else:  # no points in view
            handle_pos = view_center

        self._drag_handle_data = data_names
        self._drag_handle_offset = handle_pos - initial_timeshift
        self._plots.create_drag_cursor(handle_pos)

    def _on_timeshift_change(self, data_names: List[str]) -> None:
        self._set_data(self._data)  # TODO minimal changes in the future

    def _on_drag_cursor_drag(self, pos: float) -> None:
        self._table.set_timeshift(self._drag_handle_data, pos - self._drag_handle_offset)

    def _on_legend_checked(self) -> None:
        for plot_item, _ in self._plots._plot_item_data.items():
            if self._legend_checkbox.isChecked():
                self._legend_checkbox.setDisabled(True)
                plot_item.addLegend()
                self._plots._update_plots()

    def _make_controls(self) -> QWidget:
        button_load = QPushButton("Load CSV")
        button_load.clicked.connect(self._on_load_csv)
        button_append = QPushButton("Append CSV")
        button_append.clicked.connect(self._on_append_csv)
        self._legend_checkbox = QCheckBox("Show Legend")
        self._legend_checkbox.checkStateChanged.connect(self._on_legend_checked)
        layout = QVBoxLayout()
        layout.addWidget(button_load)
        layout.addWidget(button_append)
        layout.addWidget(self._legend_checkbox)
        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def _on_load_csv(self) -> None:
        csv_filename, _ = QFileDialog.getOpenFileName(None, "Select CSV File", filter="CSV files (*.csv)")
        if not csv_filename:  # nothing selected, user canceled
            return
        self._load_csv(csv_filename)

    def _on_append_csv(self) -> None:
        csv_filename, _ = QFileDialog.getOpenFileName(None, "Select CSV File", filter="CSV files (*.csv)")
        if not csv_filename:  # nothing selected, user canceled
            return
        self._load_csv(csv_filename, append=True)

    def _load_csv(self, csv_filepath: str, append: bool = False) -> "CsvLoaderPlotsTableWidget":
        df = pd.read_csv(csv_filepath)

        time_values = df[df.columns[0]]
        assert pd.api.types.is_numeric_dtype(time_values)

        data_dict: Dict[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]] = {}  # col header -> xs, ys
        data_type_dict: Dict[str, MultiPlotWidget.PlotType] = {}  # col header -> plot type IF NOT Default
        if append:
            for data_name, data_values in self._data.items():
                data_dict[data_name] = data_values
            for data_name, (data_color, data_type) in self._data_items.items():
                data_type_dict[data_name] = data_type

        for col_name, dtype in zip(df.columns[1:], df.dtypes[1:]):
            values = df[col_name]

            not_nans = pd.notna(values)
            if not_nans.all():
                xs = time_values
                ys = values
            else:  # get rid of nans
                xs = time_values[not_nans]
                ys = values[not_nans]
            data_dict[col_name] = (xs, ys)

            if pd.api.types.is_numeric_dtype(values):  # is numeric
                data_type = MultiPlotWidget.PlotType.DEFAULT
            else:  # assume string
                data_type = MultiPlotWidget.PlotType.ENUM_WAVEFORM
            data_type_dict[col_name] = data_type

        data_items = [(name, int_color(i), data_type) for i, (name, data_type) in enumerate(data_type_dict.items())]

        # create a new plot, because it doesn't seem possible to update plot axes in-place
        if min(cast(Sequence[int], time_values)) >= 946684800:  # Jan 1 2000, assume epoch timestamp format
            new_plots = CsvLoaderPlotsTableWidget(x_axis=lambda: TimeAxisItem(orientation="bottom"))
        else:
            new_plots = CsvLoaderPlotsTableWidget()
        new_plots.resize(1200, 800)
        new_plots._set_data_items(data_items)
        new_plots._set_data(data_dict)
        new_plots.show()

        return new_plots
