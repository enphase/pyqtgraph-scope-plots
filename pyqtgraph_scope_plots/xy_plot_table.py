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
import pyqtgraph as pg
from PySide6 import QtGui
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import QMenu, QTableWidgetItem, QMessageBox
from numpy import typing as npt

from .signals_table import ContextMenuSignalsTable, HasDataSignalsTable, HasRegionSignalsTable
from .transforms_signal_table import TransformsSignalsTable


class XyPlotWidget(pg.PlotWidget):  # type: ignore[misc]
    FADE_SEGMENTS = 16

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

        data = self._parent._data
        if isinstance(self._parent, TransformsSignalsTable):  # TODO deduplicate with PlotsTableWidget
            transformed_data = {}
            for data_name in data.keys():
                transformed = self._parent.apply_transform(data_name, data)
                if isinstance(transformed, Exception):
                    continue
                transformed_data[data_name] = data[data_name][0], transformed
            data = transformed_data

        for x_name, y_name in self._xys:
            x_xs, x_ys = data.get(x_name, (None, None))
            y_xs, y_ys = data.get(y_name, (None, None))
            y_color = self._parent._data_items.get(y_name, QColor("white"))
            if x_xs is None or x_ys is None or y_xs is None or y_ys is None:
                return
            x_lo, x_hi = HasRegionSignalsTable._indices_of_region(x_xs, self._region)
            y_lo, y_hi = HasRegionSignalsTable._indices_of_region(x_xs, self._region)
            if x_lo is None or x_hi is None or y_lo is None or y_hi is None:
                return  # empty plot
            if not np.array_equal(x_xs[x_lo:x_hi], y_xs[x_lo:x_hi]):
                print(f"X/Y indices of {x_name}, {y_name} do not match")
                return
            if x_hi - x_lo < 2:
                return

            # PyQtGraph doesn't support native fade colors, so approximate with multiple segments
            fade_segments = min(self.FADE_SEGMENTS, x_hi - x_lo)
            last_segment_end = x_lo
            segments = []
            for i in range(fade_segments):
                this_end = int(i / (fade_segments - 1) * (x_hi - x_lo)) + x_lo
                segments.append((last_segment_end, this_end))
                curve = pg.PlotCurveItem(
                    x=x_ys[last_segment_end : this_end + 1], y=y_ys[last_segment_end : this_end + 1]
                )
                last_segment_end = this_end

                segment_color = QColor(y_color)
                segment_color.setAlpha(int(i / (fade_segments - 1) * 255))
                curve.setPen(color=segment_color, width=1)
                self.addItem(curve)


class XyTable(ContextMenuSignalsTable, HasRegionSignalsTable, HasDataSignalsTable):
    """Mixin into SignalsTable that adds the option to open an XY plot in a separate window."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._xy_action = QAction("Create X-Y Plot", self)
        self._xy_action.triggered.connect(self._on_xy)
        self._xy_plots: List[XyPlotWidget] = []

        self._ordered_selects: List[QTableWidgetItem] = []
        self.itemSelectionChanged.connect(self._on_select_changed)

    def _on_select_changed(self) -> None:
        # since selectedItems is not ordered by selection, keep an internal order by tracking changes
        new_selects = [item for item in self.selectedItems() if item not in self._ordered_selects]
        self._ordered_selects = [item for item in self._ordered_selects if item in self.selectedItems()]
        self._ordered_selects.extend(new_selects)

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
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

    def _update_xys(self) -> None:
        for xy_plot in self._xy_plots:
            xy_plot.set_range(self._range)

    def _on_xy(self) -> Optional[XyPlotWidget]:
        """Creates an XY plot with the selected signal(s) and returns the new plot."""
        data = [self.item(item.row(), self.COL_NAME).text() for item in self._ordered_selects]
        if len(data) != 2:
            QMessageBox.critical(
                self, "Error", f"Select two items for X-Y plotting, got {data}", QMessageBox.StandardButton.Ok
            )
            return None
        xy_plot = XyPlotWidget(self)
        xy_plot.show()
        xy_plot.set_range(self._range)
        self._xy_plots.append(xy_plot)  # need an active reference to prevent GC'ing
        xy_plot.add_xy(data[0], data[1])
        return xy_plot

    def _on_closed_xy(self, closed: XyPlotWidget) -> None:
        self._xy_plots = [plot for plot in self._xy_plots if plot is not closed]
