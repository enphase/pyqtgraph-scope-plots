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
from typing import Type

from PySide6 import QtGui
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSplitter
from pydantic import BaseModel

from .multi_plot_widget import MultiPlotWidget
from .xy_plot import BaseXyPlot, XyPlotWidget, XyDragDroppable, XyPlotTable
from .xy_plot_refgeo import RefGeoXyPlotTable, RefGeoXyPlotWidget


class XyPlotSplitter(BaseXyPlot, QSplitter):
    """XY plot splitter with a table that otherwise passes the BaseXyPlot interface items to its plot."""

    closed = Signal()

    class FullXyPlotWidget(RefGeoXyPlotWidget, XyDragDroppable, XyPlotWidget):  # only for mixin composition
        pass

    class FullXyPlotTable(RefGeoXyPlotTable, XyPlotTable):  # only for mixin composition
        pass

    _XY_PLOT_TYPE: Type[XyPlotWidget] = FullXyPlotWidget
    _XY_PLOT_TABLE_TYPE: Type[XyPlotTable] = FullXyPlotTable

    def _make_xy_plots(self) -> XyPlotWidget:
        """Creates the XyPlot widget. self._plots is initialized by this time.
        Optionally override to create a different XyPlotWidget object"""
        return self._XY_PLOT_TYPE(self._plots)

    def _make_xy_plot_table(self) -> XyPlotTable:
        """Creates the XyPlotTable widget. self._plots and self._xy_plots are initialized by this time.
        Optionally override to create a different XyPlotTable object"""
        return self._XY_PLOT_TABLE_TYPE(self._plots, self._xy_plots)

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        self.setOrientation(Qt.Orientation.Vertical)
        self._xy_plots = self._make_xy_plots()
        self.addWidget(self._xy_plots)
        self._table = self._make_xy_plot_table()
        self.addWidget(self._table)

    def add_xy(self, x_name: str, y_name: str) -> None:
        self._xy_plots.add_xy(x_name, y_name)

    def _write_model(self, model: BaseModel) -> None:
        self._xy_plots._write_model(model)

    def _load_model(self, model: BaseModel) -> None:
        self._xy_plots._load_model(model)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.closed.emit()
