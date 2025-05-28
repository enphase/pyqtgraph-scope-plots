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
import itertools
import os.path
import time
from typing import Dict, Tuple, Any, List, Mapping, Optional, Callable, Sequence, cast

import numpy as np
import numpy.typing as npt
import pandas as pd
import pyqtgraph as pg
from PySide6 import QtWidgets
from PySide6.QtCore import QKeyCombination, QTimer
from PySide6.QtGui import QAction, QColor, Qt
from PySide6.QtWidgets import QWidget, QPushButton, QFileDialog, QMenu, QVBoxLayout, QInputDialog, QToolButton

from ..multi_plot_widget import MultiPlotWidget
from ..plots_table_widget import PlotsTableWidget
from ..search_signals_table import SearchSignalsTable
from ..signals_table import ColorPickerSignalsTable, StatsSignalsTable
from ..time_axis import TimeAxisItem
from ..timeshift_signals_table import TimeshiftSignalsTable
from ..transforms_signal_table import TransformsSignalsTable
from ..util import int_color


class CsvLoaderPlotsTableWidget(PlotsTableWidget):
    """Example app-level widget that loads CSV files into the plotter"""

    WATCH_INTERVAL_MS = 100  # polls the filesystem metadata for changes this frequently
    WATCH_STABLE_COUNT = 3  # files must be stable for this many watch cycles before refreshing

    class Plots(PlotsTableWidget.PlotsTableMultiPlots):
        """Adds legend add functionality"""

        def __init__(self, outer: "CsvLoaderPlotsTableWidget", **kwargs: Any) -> None:
            self._outer = outer
            super().__init__(**kwargs)

        def _init_plot_item(self, plot_item: pg.PlotItem) -> pg.PlotItem:
            plot_item = super()._init_plot_item(plot_item)
            if self._outer._legend_action.isChecked():
                plot_item.addLegend()
            return plot_item

        def _update_plots(self) -> None:
            super()._update_plots()
            self._outer._apply_line_width()

    class CsvSignalsTable(
        ColorPickerSignalsTable,
        PlotsTableWidget.PlotsTableSignalsTable,
        TransformsSignalsTable,
        TimeshiftSignalsTable,
        SearchSignalsTable,
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
        self._thickness: float = 1

        super().__init__()

        self._table: CsvLoaderPlotsTableWidget.CsvSignalsTable
        self._table.sigColorChanged.connect(self._on_color_changed)
        self._drag_handle_data: List[str] = []
        self._drag_handle_offset = 0.0
        self._table.sigTimeshiftHandle.connect(self._on_timeshift_handle)
        self._table.sigTimeshiftChanged.connect(self._on_timeshift_change)
        self._plots.sigDragCursorChanged.connect(self._on_drag_cursor_drag)

        self._data_csv_source: Dict[str, str] = {}  # data name -> csv path
        # csv path -> load time, modification time, stable count
        self._csv_time: Dict[str, Tuple[float, float, int]] = {}
        self._watch_timer = QTimer()
        self._watch_timer.setInterval(self.WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._check_watch)

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
        self._legend_action.setDisabled(True)  # pyqtgraph doesn't support deleting legends
        for plot_item, _ in self._plots._plot_item_data.items():
            plot_item.addLegend()
            self._plots._update_plots()

    def _on_line_width_action(self) -> None:
        value, ok = QInputDialog().getDouble(self, "Set thickness", "Line thickness", self._thickness, minValue=0)
        if not ok:
            return
        self._thickness = value
        self._apply_line_width()

    def _apply_line_width(self) -> None:
        for plot_item, _ in self._plots._plot_item_data.items():
            for item in plot_item.items:
                if isinstance(item, pg.PlotCurveItem):
                    item.setPen(color=item.opts["pen"].color(), width=self._thickness)

    def _make_controls(self) -> QWidget:
        button_load = QPushButton("Load CSV")
        button_load.clicked.connect(self._on_load_csv)
        button_append = QToolButton()
        button_append.setText("Append CSV")
        button_append.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button_append.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)
        button_append.clicked.connect(self._on_append_csv)
        menu_append = QMenu(self)
        action_refresh = QAction(menu_append)
        action_refresh.setText("Refresh CSV")
        action_refresh.setShortcut(QKeyCombination(Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_F5))
        action_refresh.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action_refresh.triggered.connect(self._on_refresh_csv)
        self.addAction(action_refresh)
        menu_append.addAction(action_refresh)
        self._action_watch = QAction(menu_append)
        self._action_watch.setText("Set Watch")
        self._action_watch.setCheckable(True)
        self._action_watch.toggled.connect(self._on_toggle_watch)
        menu_append.addAction(self._action_watch)
        button_append.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        button_append.setArrowType(Qt.ArrowType.DownArrow)
        button_append.setMenu(menu_append)

        button_visuals = QPushButton("Visual Settings")
        button_menu = QMenu(self)
        self._legend_action = QAction("Show Legend", button_menu)
        self._legend_action.setCheckable(True)
        self._legend_action.toggled.connect(self._on_legend_checked)
        button_menu.addAction(self._legend_action)
        line_width_action = QAction("Set Line Width", button_menu)
        line_width_action.triggered.connect(self._on_line_width_action)
        button_menu.addAction(line_width_action)
        button_visuals.setMenu(button_menu)

        layout = QVBoxLayout()
        layout.addWidget(button_load)
        layout.addWidget(button_append)
        layout.addWidget(button_visuals)
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

    def _on_refresh_csv(self) -> None:
        """Reloads all CSVs. Discards data (but not data items) that are no longer present in the reloaded CSVs.
        Does not modify data items (new data items are discarded)."""
        csv_data_items = {
            key: [pair[0] for pair in pairs]
            for key, pairs in itertools.groupby(self._data_csv_source.items(), lambda item: item[1])
        }
        for csv_filename, curr_data_items in csv_data_items.items():
            self._load_csv(csv_filename, colnames=curr_data_items, append=True)

    def _on_toggle_watch(self) -> None:
        if self._action_watch.isChecked():
            self._watch_timer.start()
        else:
            self._watch_timer.stop()

    def _check_watch(self) -> None:
        csv_data_items = {
            key: [pair[0] for pair in pairs]
            for key, pairs in itertools.groupby(self._data_csv_source.items(), lambda item: item[1])
        }
        for csv_filename, curr_data_items in csv_data_items.items():
            if csv_filename not in self._csv_time:  # skip files where the load time is unknown
                continue
            if not os.path.exists(csv_filename):  # ignore transiently missing files
                continue
            csv_load_time, csv_modify_time, csv_stable_count = self._csv_time[csv_filename]
            new_modify_time = os.path.getmtime(csv_filename)
            if new_modify_time <= csv_load_time:
                continue
            if new_modify_time != csv_modify_time:
                csv_stable_count = 0
            else:
                csv_stable_count += 1

            if csv_stable_count >= self.WATCH_STABLE_COUNT:
                self._load_csv(csv_filename, colnames=curr_data_items, append=True)
            else:  # update record
                self._csv_time[csv_filename] = csv_load_time, new_modify_time, csv_stable_count

    def _load_csv(
        self, csv_filepath: str, append: bool = False, colnames: Optional[List[str]] = None
    ) -> "CsvLoaderPlotsTableWidget":
        """Loads a CSV file into the current window.
        If append is true, preserves the existing data / metadata.
        If colnames is not None, reads the specified column names from the file. These must already be in the dataset.
        Items in colnames but not in the file are read as an empty table
        """
        df = pd.read_csv(csv_filepath)

        time_values = df[df.columns[0]]
        assert pd.api.types.is_numeric_dtype(time_values)

        data_dict: Dict[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]] = {}  # col header -> xs, ys
        data_type_dict: Dict[str, MultiPlotWidget.PlotType] = {}  # col header -> plot type IF NOT Default
        data_csv_source: Dict[str, str] = {}
        if append:
            data_dict.update(self._data)
            data_type_dict.update(
                {data_name: data_type for data_name, (data_color, data_type) in self._data_items.items()}
            )
            data_csv_source.update(self._data_csv_source)

        if colnames is not None:
            for data_name in colnames:  # clear colnames data is specified
                data_dict[data_name] = (np.array([]), np.array([]))
                assert data_name in data_type_dict  # keeps prior value

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
            data_csv_source[col_name] = csv_filepath

            if pd.api.types.is_numeric_dtype(values):  # is numeric
                data_type = MultiPlotWidget.PlotType.DEFAULT
            else:  # assume string
                data_type = MultiPlotWidget.PlotType.ENUM_WAVEFORM
            data_type_dict[col_name] = data_type

        data_items = [(name, int_color(i), data_type) for i, (name, data_type) in enumerate(data_type_dict.items())]

        # if not in append mode, check if a time axis is needed - inferring by if min is Jan 1 2000 in timestamp
        if not append and min(cast(Sequence[int], time_values)) >= 946684800:
            self._plots.set_x_axis(lambda: TimeAxisItem(orientation="bottom"))

        self._set_data_items(data_items)
        self._set_data(data_dict)
        self._data_csv_source = data_csv_source
        self._csv_time[csv_filepath] = (time.time(), time.time(), 0)

        return self
