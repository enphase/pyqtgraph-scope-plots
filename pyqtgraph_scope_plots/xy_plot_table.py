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

from typing import Any, List, Tuple, Mapping, Optional, Literal, Union, cast

import numpy as np
import pyqtgraph as pg
from PySide6 import QtGui
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QColor, QDragMoveEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QMenu, QMessageBox
from numpy import typing as npt
from pydantic import BaseModel

from .save_restore_model import HasSaveLoadConfig, BaseTopModel
from .multi_plot_widget import DragTargetOverlay
from .signals_table import ContextMenuSignalsTable, HasDataSignalsTable, HasRegionSignalsTable, DraggableSignalsTable
from .transforms_signal_table import TransformsSignalsTable


class XyPlotWidget(pg.PlotWidget):  # type: ignore[misc]
    FADE_SEGMENTS = 16

    def __init__(self, parent: "XyTable"):
        super().__init__()
        self._parent = parent
        self._xys: List[Tuple[str, str]] = []
        self._region = (-float("inf"), float("inf"))

        self._drag_overlays: List[DragTargetOverlay] = []
        self.setAcceptDrops(True)

    def add_xy(self, x_name: str, y_name: str) -> None:
        if (x_name, y_name) not in self._xys:
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
            x_ts, x_ys = data.get(x_name, (None, None))
            y_ts, y_ys = data.get(y_name, (None, None))
            if x_ts is None or x_ys is None or y_ts is None or y_ys is None:
                continue

            # truncate to smaller series, if needed
            region_lo = max(self._region[0], x_ts[0], y_ts[0])
            region_hi = min(self._region[1], x_ts[-1], y_ts[-1])

            xt_lo, xt_hi = HasRegionSignalsTable._indices_of_region(x_ts, (region_lo, region_hi))
            yt_lo, yt_hi = HasRegionSignalsTable._indices_of_region(y_ts, (region_lo, region_hi))
            if xt_lo is None or xt_hi is None or yt_lo is None or yt_hi is None or xt_hi - xt_lo < 2:
                continue  # empty plot

            # correct for floating point imprecision in indices
            if (xt_hi - xt_lo) == (yt_hi - yt_lo) + 1:  # delete an extra x-point
                if abs(y_ts[yt_lo] - x_ts[xt_lo]) > abs(y_ts[yt_hi - 1] - x_ts[xt_hi - 1]):  # larger delta on low point
                    xt_lo = xt_lo + 1
                else:
                    xt_hi = xt_hi - 1
            elif (xt_hi - xt_lo) + 1 == (yt_hi - yt_lo):  # delete an extra y-point
                if abs(y_ts[yt_lo] - x_ts[xt_lo]) > abs(y_ts[yt_hi - 1] - x_ts[xt_hi - 1]):  # larger delta on low point
                    yt_lo = yt_lo + 1
                else:
                    yt_hi = yt_hi - 1
            if (xt_hi - xt_lo) != (yt_hi - yt_lo):
                print(f"X/Y indices of {x_name}, {y_name} do not have same length")
                continue
            x_indices = x_ts[xt_lo:xt_hi]
            y_indices = y_ts[yt_lo:yt_hi]
            if max(abs(y_indices - x_indices)) > (y_indices[1] - y_indices[0]) / 1000:
                print(f"X/Y indices of {x_name}, {y_name} do not match")
                continue

            # PyQtGraph doesn't support native fade colors, so approximate with multiple segments
            y_color = self._parent._data_items.get(y_name, QColor("white"))
            fade_segments = min(
                self.FADE_SEGMENTS, xt_hi - xt_lo
            )  # keep track of the x time indices, apply offset for y time indices
            last_segment_end = xt_lo
            for i in range(fade_segments):
                this_end = int(i / (fade_segments - 1) * (xt_hi - xt_lo)) + xt_lo
                curve = pg.PlotCurveItem(
                    x=x_ys[last_segment_end:this_end],
                    y=y_ys[last_segment_end + yt_lo - xt_lo : this_end + yt_lo - xt_lo],
                )
                # make sure segments are continuous since this_end is exclusive,
                # but only as far as the beginning of this segment
                last_segment_end = max(last_segment_end, this_end - 1)

                segment_color = QColor(y_color)
                segment_color.setAlpha(int(i / (fade_segments - 1) * 255))
                curve.setPen(color=segment_color, width=1)
                self.addItem(curve)

    def dragEnterEvent(self, event: QDragMoveEvent) -> None:
        if not event.mimeData().data(DraggableSignalsTable.DRAG_MIME_TYPE):  # check for right type
            return
        overlay = DragTargetOverlay(self)
        overlay.resize(QSize(self.width(), self.height()))
        overlay.setVisible(True)
        self._drag_overlays.append(overlay)
        event.accept()

    def _clear_drag_overlays(self) -> None:
        for drag_overlay in self._drag_overlays:
            drag_overlay.deleteLater()
        self._drag_overlays = []

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._clear_drag_overlays()

    def dropEvent(self, event: QDropEvent) -> None:
        self._clear_drag_overlays()

        data = event.mimeData().data(DraggableSignalsTable.DRAG_MIME_TYPE)
        if not data:
            return
        drag_data_names = bytes(data.data()).decode("utf-8").split("\0")
        if len(drag_data_names) != 2:
            QMessageBox.critical(
                self,
                "Error",
                f"Select two items for X-Y plotting, got {drag_data_names}",
                QMessageBox.StandardButton.Ok,
            )
            return
        self.add_xy(drag_data_names[0], drag_data_names[1])
        event.accept()


class XyWindowModel(BaseModel):
    xy_data_items: List[Tuple[str, str]] = []  # list of (x, y) data items
    x_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None
    y_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None


class XyTableStateModel(BaseTopModel):
    xy_windows: Optional[List[XyWindowModel]] = None


class XyTable(
    DraggableSignalsTable, ContextMenuSignalsTable, HasRegionSignalsTable, HasDataSignalsTable, HasSaveLoadConfig
):
    """Mixin into SignalsTable that adds the option to open an XY plot in a separate window."""

    TOP_MODEL_BASES = [XyTableStateModel]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._xy_action = QAction("Create X-Y Plot", self)
        self._xy_action.triggered.connect(self._on_create_xy)
        self._xy_plots: List[XyPlotWidget] = []

    def _write_model(self, model: BaseTopModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyTableStateModel)
        model.xy_windows = []
        for xy_plot in self._xy_plots:
            xy_window_model = XyWindowModel(xy_data_items=xy_plot._xys)
            viewbox = cast(pg.PlotItem, xy_plot.getPlotItem()).getViewBox()
            if viewbox.autoRangeEnabled()[0]:
                xy_window_model.x_range = "auto"
            else:
                xy_window_model.x_range = tuple(viewbox.viewRange()[0])
            if viewbox.autoRangeEnabled()[1]:
                xy_window_model.y_range = "auto"
            else:
                xy_window_model.y_range = tuple(viewbox.viewRange()[1])
            model.xy_windows.append(xy_window_model)

    def _load_model(self, model: BaseTopModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyTableStateModel)
        if model.xy_windows is None:
            return
        for xy_plot in self._xy_plots:  # remove all existing plots
            xy_plot.close()
        for xy_window_model in model.xy_windows:  # create plots from model
            xy_plot = self.create_xy()
            for xy_data_item in xy_window_model.xy_data_items:
                xy_plot.add_xy(*xy_data_item)
            viewbox = cast(pg.PlotItem, xy_plot.getPlotItem()).getViewBox()
            if xy_window_model.x_range is not None and xy_window_model.x_range != "auto":
                viewbox.setXRange(xy_window_model.x_range[0], xy_window_model.x_range[1], 0)
            if xy_window_model.y_range is not None and xy_window_model.y_range != "auto":
                viewbox.setYRange(xy_window_model.y_range[0], xy_window_model.y_range[1], 0)
            if xy_window_model.x_range == "auto" or xy_window_model.y_range == "auto":
                viewbox.enableAutoRange(
                    x=xy_window_model.x_range == "auto" or None, y=xy_window_model.y_range == "auto" or None
                )

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

    def _on_create_xy(self) -> Optional[XyPlotWidget]:
        """Creates an XY plot with the selected signal(s) and returns the new plot."""
        data = [self.item(item.row(), self.COL_NAME).text() for item in self._ordered_selects]
        if len(data) != 2:
            QMessageBox.critical(
                self, "Error", f"Select two items for X-Y plotting, got {data}", QMessageBox.StandardButton.Ok
            )
            return None
        xy_plot = self.create_xy()
        xy_plot.add_xy(data[0], data[1])
        return xy_plot

    def create_xy(self) -> XyPlotWidget:
        """Creates and opens an empty XY plot widget."""
        xy_plot = XyPlotWidget(self)
        xy_plot.show()
        xy_plot.set_range(self._range)
        self._xy_plots.append(xy_plot)  # need an active reference to prevent GC'ing
        return xy_plot

    def _on_closed_xy(self, closed: XyPlotWidget) -> None:
        self._xy_plots = [plot for plot in self._xy_plots if plot is not closed]
