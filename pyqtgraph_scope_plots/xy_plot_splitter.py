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
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QMessageBox, QWidget, QSplitter, QTableWidget
from numpy import typing as npt
from pydantic import BaseModel

from .save_restore_model import HasSaveLoadConfig, BaseTopModel
from .signals_table import ContextMenuSignalsTable, HasDataSignalsTable, HasRegionSignalsTable, DraggableSignalsTable
from .xy_plot import BaseXyPlot, XyPlotWidget, XyWindowModel


class XyPlotSplitter(BaseXyPlot, QSplitter):
    def __init__(self, table_parent: "XyTable"):
        super().__init__(table_parent=table_parent)
        self.setOrientation(Qt.Orientation.Vertical)
        self._plots = XyPlotWidget(table_parent=table_parent)
        self.addWidget(self._plots)
        self._table = QTableWidget()
        self.addWidget(self._table)

    def add_xy(self, x_name: str, y_name: str) -> None:
        self._plots.add_xy(x_name, y_name)

    def set_range(self, region: Tuple[float, float]) -> None:
        self._plots.set_range(region)

    def _write_model(self, model: BaseModel) -> None:
        self._plots._write_model(model)

    def _load_model(self, model: BaseModel) -> None:
        self._plots._load_model(model)
