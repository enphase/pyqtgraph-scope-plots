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

from PySide6 import QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSplitter, QTableWidget, QTableWidgetItem
from pydantic import BaseModel

from .multi_plot_widget import MultiPlotWidget
from .signals_table import SignalsTable
from .xy_plot import BaseXyPlot, XyPlotWidget


class XyPlotTable(QTableWidget):
    COL_X_NAME: int = 0
    COL_Y_NAME: int = 1

    def __init__(self, plots: MultiPlotWidget, xy_plots: XyPlotWidget):
        super().__init__()
        self._plots = plots
        self._xy_plots = xy_plots

        self._plots.sigDataItemsUpdated.connect(self._update)
        self._xy_plots.sigXysChanged.connect(self._update)

        self.setColumnCount(2)
        self.setHorizontalHeaderItem(self.COL_X_NAME, QTableWidgetItem("X"))
        self.setHorizontalHeaderItem(self.COL_Y_NAME, QTableWidgetItem("Y"))

    def _update(self):
        self.setRowCount(0)  # clear table
        self.setRowCount(len(self._xy_plots._xys))
        for row, (x_name, y_name) in enumerate(self._xy_plots._xys):
            x_item = SignalsTable._create_noneditable_table_item()
            x_item.setText(x_name)
            x_color, _ = self._plots._data_items.get(x_name, (None, None))
            if x_color is not None:
                x_item.setForeground(x_color)
            self.setItem(row, self.COL_X_NAME, x_item)

            y_item = SignalsTable._create_noneditable_table_item()
            y_item.setText(y_name)
            y_color, _ = self._plots._data_items.get(y_name, (None, None))
            if y_color is not None:
                y_item.setForeground(y_color)
            self.setItem(row, self.COL_Y_NAME, y_item)


class XyPlotSplitter(BaseXyPlot, QSplitter):
    closed = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        self.setOrientation(Qt.Orientation.Vertical)
        self._xy_plots = XyPlotWidget(plots)
        self.addWidget(self._xy_plots)
        self._table = XyPlotTable(plots, self._xy_plots)
        self.addWidget(self._table)

    def add_xy(self, x_name: str, y_name: str) -> None:
        self._xy_plots.add_xy(x_name, y_name)

    def _write_model(self, model: BaseModel) -> None:
        self._xy_plots._write_model(model)

    def _load_model(self, model: BaseModel) -> None:
        self._xy_plots._load_model(model)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit()
