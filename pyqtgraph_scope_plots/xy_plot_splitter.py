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

from typing import Any, List, Tuple, Mapping, Optional

import numpy as np
from PySide6 import QtGui
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget, QSplitter, QTableWidget
from numpy import typing as npt
from pydantic import BaseModel

from .multi_plot_widget import MultiPlotWidget
from .save_restore_model import HasSaveLoadConfig, BaseTopModel
from .signals_table import ContextMenuSignalsTable, HasDataSignalsTable, HasRegionSignalsTable, DraggableSignalsTable
from .xy_plot import BaseXyPlot, XyPlotWidget, XyWindowModel


class XyPlotTable(QTableWidget):
    def __init__(self, plot_widget: XyPlotWidget):
        super().__init__()
        self._plot_widget = plot_widget


class XyPlotSplitter(BaseXyPlot, QSplitter):
    closed = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        self.setOrientation(Qt.Orientation.Vertical)
        self._xy_plots = XyPlotWidget(plots)
        self.addWidget(self._xy_plots)
        self._table = XyPlotTable(self._xy_plots)
        self.addWidget(self._table)

    def add_xy(self, x_name: str, y_name: str) -> None:
        self._xy_plots.add_xy(x_name, y_name)

    def set_range(self, region: Tuple[float, float]) -> None:
        self._xy_plots.set_range(region)

    def _write_model(self, model: BaseModel) -> None:
        self._xy_plots._write_model(model)

    def _load_model(self, model: BaseModel) -> None:
        self._xy_plots._load_model(model)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.closed.emit()
