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

from typing import Any, List, Tuple, Mapping

import numpy as np
import pyqtgraph as pg
from PySide6 import QtGui
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QMenu
from numpy import typing as npt

from .signals_table import ContextMenuSignalsTable, HasDataSignalsTable, HasRegionSignalsTable


class XyPlotWidget(pg.PlotWidget):  # type: ignore[misc]
    def __init__(self, parent: "XyTable"):
        super().__init__()
        self._parent = parent
        self._xys: List[Tuple[str, str]] = []
        self._region = (-float("inf"), float("inf"))

    def add_xy(self, x_name: str, y_name: str) -> None:
        self._xys.append((x_name, y_name))
        self._update()

    def set_range(self, region: Tuple[float, float]) -> None:
        self._region = region
        self._update()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._parent._on_closed_xy(self)

    def _update(self) -> None:
        for data_item in self.listDataItems():  # clear existing
            self.removeItem(data_item)

        for x_name, y_name in self._xys:
            x_xs, x_ys = self._parent._data.get(x_name, (None, None))
            y_xs, y_ys = self._parent._data.get(y_name, (None, None))
            y_color = self._parent._data_items.get(y_name, QColor("white"))
            if x_xs is None or x_ys is None or y_xs is None or y_ys is None:
                return
            x_lo, x_hi = HasRegionSignalsTable._indices_of_region(x_xs, self._region)
            y_lo, y_hi = HasRegionSignalsTable._indices_of_region(x_xs, self._region)
            if x_lo is None or x_hi is None or y_lo is None or y_hi is None:
                return  # empty plot
            assert np.array_equal(x_xs[x_lo:x_hi], y_xs[x_lo:x_hi]), "TODO support resampling"

            curve = pg.PlotCurveItem(x=x_ys[x_lo:x_hi], y=y_ys[x_lo:x_hi])
            curve.setPen(color=y_color, width=1)
            self.addItem(curve)


class XyTable(ContextMenuSignalsTable, HasRegionSignalsTable, HasDataSignalsTable):
    """Mixin into SignalsTable that adds the option to open an XY plot in a separate window."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._xy_action = QAction("Create X-Y Plot", self)
        self._xy_action.triggered.connect(self._on_xy)
        self._xy_plots: List[XyPlotWidget] = []

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        rows = list(set([item.row() for item in self.selectedItems()]))
        self._xy_action.setDisabled(len(rows) != 2)
        menu.addAction(self._xy_action)

    def set_range(self, range: Tuple[float, float]) -> None:
        super().set_range(range)
        self._update_xys()

    def set_data(
        self,
        data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]],
    ) -> None:
        super().set_data(data)
        self._update_xys()

    def _update_xys(self):
        for xy_plot in self._xy_plots:
            xy_plot.set_range(self._range)

    def _on_xy(self) -> XyPlotWidget:
        """Creates an XY plot with the selected signal(s) and returns the new plot."""
        data = list(set([self.item(item.row(), self.COL_NAME).text() for item in self.selectedItems()]))
        assert len(data) == 2
        plot = XyPlotWidget(self)
        plot.show()
        plot.add_xy(data[0], data[1])
        self._xy_plots.append(plot)  # need an active reference to prevent GC'ing
        return plot

    def _on_closed_xy(self, closed: XyPlotWidget):
        self._xy_plots = [plot for plot in self._xy_plots if plot is not closed]
