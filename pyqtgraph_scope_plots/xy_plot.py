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

from typing import List, Tuple, Optional, Literal, Union, cast, Any, Dict, Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Signal, QPoint
from PySide6.QtGui import QColor, QDragMoveEvent, QDragLeaveEvent, QDropEvent, Qt
from PySide6.QtWidgets import QMessageBox, QWidget, QTableWidget, QTableWidgetItem, QMenu
from numpy import typing as npt
from pydantic import BaseModel

from .save_restore_model import HasSaveLoadConfig
from .multi_plot_widget import DragTargetOverlay, MultiPlotWidget, LinkedMultiPlotWidget
from .signals_table import HasRegionSignalsTable, DraggableSignalsTable, SignalsTable


class XyWindowModel(BaseModel):
    xy_data_items: List[Tuple[str, str]] = []  # list of (x, y) data items
    x_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None
    y_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None


class BaseXyPlot(HasSaveLoadConfig):
    """Abstract interface for a XY plot widget"""

    _MODEL_BASES = [XyWindowModel]
    closed = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__()
        self._plots = plots

    def add_xy(self, x_name: str, y_name: str) -> None:
        """Adds a XY plot to the widget"""
        ...


class XyPlotWidget(BaseXyPlot, pg.PlotWidget):  # type: ignore[misc]
    _FADE_SEGMENTS = 16

    sigXyDataItemsChanged = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        self._xys: List[Tuple[str, str]] = []

        plots.sigDataUpdated.connect(self._update)
        if isinstance(self._plots, LinkedMultiPlotWidget):
            plots.sigCursorRangeChanged.connect(self._update)

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, XyWindowModel)
        model.xy_data_items = self._xys
        viewbox = cast(pg.PlotItem, self.getPlotItem()).getViewBox()
        if viewbox.autoRangeEnabled()[0]:
            model.x_range = "auto"
        else:
            model.x_range = tuple(viewbox.viewRange()[0])
        if viewbox.autoRangeEnabled()[1]:
            model.y_range = "auto"
        else:
            model.y_range = tuple(viewbox.viewRange()[1])

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, XyWindowModel)
        for xy_data_item in model.xy_data_items:
            self.add_xy(*xy_data_item)
        viewbox = cast(pg.PlotItem, self.getPlotItem()).getViewBox()
        if model.x_range is not None and model.x_range != "auto":
            viewbox.setXRange(model.x_range[0], model.x_range[1], 0)
        if model.y_range is not None and model.y_range != "auto":
            viewbox.setYRange(model.y_range[0], model.y_range[1], 0)
        if model.x_range == "auto" or model.y_range == "auto":
            viewbox.enableAutoRange(x=model.x_range == "auto" or None, y=model.y_range == "auto" or None)

    def add_xy(self, x_name: str, y_name: str) -> None:
        if (x_name, y_name) not in self._xys:
            self._xys.append((x_name, y_name))
            self._update()
        self.sigXyDataItemsChanged.emit()

    def _get_region(self) -> Tuple[float, float]:
        """Gets the currently selected region from the plot, or (-inf, inf) by default."""
        if isinstance(self._plots, LinkedMultiPlotWidget) and isinstance(self._plots._last_region, tuple):
            return self._plots._last_region
        else:
            return (-float("inf"), float("inf"))

    @staticmethod
    def _get_correlated_indices(
        x_ts: npt.NDArray[np.float64], y_ts: npt.NDArray[np.float64], start: float, end: float
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Find the indices containing start and end for x_ts and y_ts, if they are correlated
        (evaluate to approximate the same values, and of the same size)"""
        xt_lo, xt_hi = HasRegionSignalsTable._indices_of_region(x_ts, (start, end))
        yt_lo, yt_hi = HasRegionSignalsTable._indices_of_region(y_ts, (start, end))
        if xt_lo is None or xt_hi is None or yt_lo is None or yt_hi is None or xt_hi - xt_lo < 2:
            return None

        if (xt_hi - xt_lo) != (yt_hi - yt_lo):
            return None
        x_indices = x_ts[xt_lo:xt_hi]
        y_indices = y_ts[yt_lo:yt_hi]
        if max(abs(y_indices - x_indices)) > (y_indices[1] - y_indices[0]) / 1000:
            return None
        return (xt_lo, xt_hi), (yt_lo, yt_hi)

    def _update(self) -> None:
        for data_item in self.listDataItems():  # clear existing
            self.removeItem(data_item)

        region = self._get_region()
        data = self._plots._data
        for x_name, y_name in self._xys:
            x_ts, x_ys = data.get(x_name, (None, None))
            y_ts, y_ys = data.get(y_name, (None, None))
            if x_ts is None or x_ys is None or y_ts is None or y_ys is None:
                continue

            # truncate to smaller series, if needed
            region_lo = max(region[0], x_ts[0], y_ts[0])
            region_hi = min(region[1], x_ts[-1], y_ts[-1])
            indices = self._get_correlated_indices(x_ts, y_ts, region_lo, region_hi)
            if indices is None:
                print(f"X/Y indices of {x_name}, {y_name} empty or do not match")
                continue
            (xt_lo, xt_hi), (yt_lo, yt_hi) = indices

            # PyQtGraph doesn't support native fade colors, so approximate with multiple segments
            y_color, _ = self._plots._data_items.get(y_name, (QColor("white"), None))
            fade_segments = min(
                self._FADE_SEGMENTS, xt_hi - xt_lo
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


class XyDragDroppable(BaseXyPlot):
    """Mixin to BaseXyPlot that adds XYs from a drag-drop action from the signals table.
    This MUST be mixed into a QWidget subclass, but mypy can't encode the type dependency."""

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        assert isinstance(self, QWidget)

        self._drag_overlays: List[DragTargetOverlay] = []
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragMoveEvent) -> None:
        assert isinstance(self, QWidget)
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
            assert isinstance(self, QWidget)
            QMessageBox.critical(
                self,
                "Error",
                f"Select two items for X-Y plotting, got {drag_data_names}",
                QMessageBox.StandardButton.Ok,
            )
            return
        self.add_xy(drag_data_names[0], drag_data_names[1])
        event.accept()


class XyPlotTable(QTableWidget):
    COL_X_NAME: int = 0
    COL_Y_NAME: int = 1

    def __init__(self, plots: MultiPlotWidget, xy_plots: XyPlotWidget):
        super().__init__()
        self._plots = plots
        self._xy_plots = xy_plots

        self._plots.sigDataItemsUpdated.connect(self._update)
        self._xy_plots.sigXyDataItemsChanged.connect(self._update)

        self.setColumnCount(2)
        self.setHorizontalHeaderItem(self.COL_X_NAME, QTableWidgetItem("X"))
        self.setHorizontalHeaderItem(self.COL_Y_NAME, QTableWidgetItem("Y"))

    def _update(self) -> None:
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


class ContextMenuXyPlotTable(XyPlotTable):
    """Mixin into XyPlotTable that adds a context menu on rows."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._spawn_table_cell_menu)

    def _spawn_table_cell_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        self._populate_context_menu(menu)
        menu.popup(self.mapToGlobal(pos))

    def _populate_context_menu(self, menu: QMenu) -> None:
        """Called when the context menu is created, to populate its items."""
        pass
