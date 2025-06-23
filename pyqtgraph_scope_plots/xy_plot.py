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
from abc import abstractmethod
import bisect
from typing import List, Tuple, Optional, Literal, Union, cast, Any, Dict

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Signal, QPoint
from PySide6.QtGui import QColor, QDragMoveEvent, QDragLeaveEvent, QDropEvent, Qt, QAction
from PySide6.QtWidgets import QMessageBox, QWidget, QTableWidgetItem, QMenu
from numpy import typing as npt
from pydantic import BaseModel

from .interactivity_mixins import LiveCursorPlot
from .multi_plot_widget import DragTargetOverlay, MultiPlotWidget, LinkedMultiPlotWidget
from .util import HasSaveLoadConfig, MixinColsTable
from .signals_table import HasRegionSignalsTable, DraggableSignalsTable, SignalsTable


class XyWindowModel(BaseModel):
    xy_data_items: List[Tuple[str, str]] = []  # list of (x, y) data items
    x_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None
    y_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None


class BaseXyPlot(HasSaveLoadConfig):
    """Abstract interface for a XY plot widget"""

    _TOP_MODEL_NAME = "TopXyWindowModel"
    _MODEL_BASES = [XyWindowModel]
    sigClosed = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__()
        self._plots = plots

    @abstractmethod
    def add_xy(self, x_name: str, y_name: str) -> None:
        """Adds a XY plot to the widget"""
        ...

    @abstractmethod
    def remove_xy(self, x_name: str, y_name: str) -> None:
        """Removes a XY plot from the widget. Asserts out if the plot doesn't exist."""
        ...

    @abstractmethod
    def get_plot_widget(self) -> "XyPlotWidget":
        """Returns the plot widget, for example if this is a plot + table splitter widget."""
        ...


class XyPlotWidget(BaseXyPlot, pg.PlotWidget):  # type: ignore[misc]
    _FADE_SEGMENTS = 16

    sigXyDataItemsChanged = Signal()

    def __init__(self, plots: MultiPlotWidget):
        super().__init__(plots)
        self._xys: List[Tuple[str, str]] = []
        self._xy_curves: Dict[Tuple[str, str], List[pg.PlotCurveItem]] = {}

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

    def remove_xy(self, x_name: str, y_name: str) -> None:
        self._xys.remove((x_name, y_name))
        self._update()
        self.sigXyDataItemsChanged.emit()

    def get_plot_widget(self) -> "XyPlotWidget":
        return self

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
        self._xy_curves = {}

        region = HasRegionSignalsTable._region_of_plot(self._plots)
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

            this_curve_list = self._xy_curves.setdefault((x_name, y_name), [])
            # PyQtGraph doesn't support native fade colors, so approximate with multiple segments
            y_color, _ = self._plots._data_items.get(y_name, (QColor("white"), None))
            fade_segments = min(
                self._FADE_SEGMENTS, xt_hi - xt_lo
            )  # keep track of the x time indices, apply offset for y time indices
            last_segment_end = xt_lo
            for i in range(fade_segments):
                this_end = int(i / (fade_segments - 1) * (xt_hi - xt_lo)) + xt_lo
                if i == fade_segments - 1:
                    curve_kwargs = {"name": f"{x_name} (x), {y_name} (y)"}
                else:
                    curve_kwargs = {}
                curve = pg.PlotCurveItem(
                    x=x_ys[last_segment_end:this_end],
                    y=y_ys[last_segment_end + yt_lo - xt_lo : this_end + yt_lo - xt_lo],
                    **curve_kwargs,
                )
                # make sure segments are continuous since this_end is exclusive,
                # but only as far as the beginning of this segment
                last_segment_end = max(last_segment_end, this_end - 1)

                segment_color = QColor(
                    y_color.red() * (i + 1) // self._FADE_SEGMENTS,
                    y_color.green() * (i + 1) // self._FADE_SEGMENTS,
                    y_color.blue() * (i + 1) // self._FADE_SEGMENTS,
                )
                curve.setPen(color=segment_color, width=1)
                self.addItem(curve)
                this_curve_list.append(curve)

    def _get_visible_xys_at_t(self, t: float) -> List[Tuple[float, float, QColor]]:
        """For a t, return all points (with color) on visible curves."""
        if (
            isinstance(self._plots, LinkedMultiPlotWidget)
            and isinstance(self._plots._last_region, tuple)
            and (t < self._plots._last_region[0] or t > self._plots._last_region[1])
        ):
            return []

        outputs = []
        for x_name, y_name in self._xys:
            xy_curves = self._xy_curves.get((x_name, y_name), [])
            if not any(xy_curve.isVisible() for xy_curve in xy_curves):
                continue
            x_ts, x_ys = self._plots._data.get(x_name, ([], []))
            y_ts, y_ys = self._plots._data.get(y_name, ([], []))
            x_index = bisect.bisect_left(x_ts, t)
            y_index = bisect.bisect_left(y_ts, t)
            if x_index >= len(x_ts) or y_index >= len(y_ts) or x_ts[x_index] != t or y_ts[y_index] != t:
                continue
            color, _ = self._plots._data_items.get(y_name, (QColor("white"), None))
            outputs.append((x_ys[x_index], y_ys[y_index], color))
        return outputs


class XyPlotLinkedCursorWidget(XyPlotWidget):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        assert isinstance(self._plots, LinkedMultiPlotWidget)
        self._hover_pts: List[pg.ScatterPlotItem] = []

        self._plots.sigHoverCursorChanged.connect(self._on_linked_hover_cursor_change)

    def _update(self) -> None:
        super()._update()
        self._on_linked_hover_cursor_change()  # generate initial points

    def _on_linked_hover_cursor_change(self) -> None:
        assert isinstance(self._plots, LinkedMultiPlotWidget)
        for pts in self._hover_pts:  # clear old widgets as needed, then re-create
            self.removeItem(pts)
        self._hover_pts = []

        t = self._plots._last_hover
        if t is None:
            return
        for x, y, color in self._get_visible_xys_at_t(t):
            hover_pt = pg.ScatterPlotItem(x=[x], y=[y], symbol="o", brush=color)
            hover_pt.setZValue(LiveCursorPlot._Z_VALUE_HOVER_TARGET)
            self.addItem(hover_pt, ignoreBounds=True)
            self._hover_pts.append(hover_pt)


class XyPlotLinkedPoiWidget(XyPlotWidget):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        assert isinstance(self._plots, LinkedMultiPlotWidget)
        self._poi_pts: List[pg.ScatterPlotItem] = []

        self._plots.sigPoiChanged.connect(self._on_linked_poi_change)

    def _update(self) -> None:
        super()._update()
        self._on_linked_poi_change()  # generate initial points

    def _on_linked_poi_change(self) -> None:
        assert isinstance(self._plots, LinkedMultiPlotWidget)
        for pts in self._poi_pts:  # clear old widgets as needed, then re-create
            self.removeItem(pts)
        self._poi_pts = []

        for t in self._plots._last_pois:
            for x, y, color in self._get_visible_xys_at_t(t):
                poi_pt = pg.ScatterPlotItem(x=[x], y=[y], symbol="o", brush=color)
                self.addItem(poi_pt, ignoreBounds=True)
                self._poi_pts.append(poi_pt)


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


class XyPlotTable(MixinColsTable):
    COL_X_NAME: int = -1
    COL_Y_NAME: int = -1

    def _post_cols(self) -> int:  # total number of columns, including _pre_cols
        self.COL_X_NAME = super()._post_cols()
        self.COL_Y_NAME = self.COL_X_NAME + 1
        return self.COL_Y_NAME + 1

    def _init_table(self) -> None:
        super()._init_table()
        self.setHorizontalHeaderItem(self.COL_X_NAME, QTableWidgetItem("X"))
        self.setHorizontalHeaderItem(self.COL_Y_NAME, QTableWidgetItem("Y"))

    def __init__(self, plots: MultiPlotWidget, xy_plots: XyPlotWidget):
        super().__init__()
        self._plots = plots
        self._xy_plots = xy_plots

        self._plots.sigDataItemsUpdated.connect(self._update)
        self._xy_plots.sigXyDataItemsChanged.connect(self._update)

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
        """IMPLEMENT ME. Called when the context menu is created, to populate its items."""
        pass


class DeleteableXyPlotTable(ContextMenuXyPlotTable):
    """Mixin into XyPlotTable that adds a hook for item deletion, both as hotkey and from a context menu."""

    _DELETE_ACTION_NAME = "Remove"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._delete_row_action = QAction(self._DELETE_ACTION_NAME or "", self)
        self._delete_row_action.setShortcut(Qt.Key.Key_Delete)
        self._delete_row_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)  # require widget focus to fire

        def on_delete_rows() -> None:
            rows = list(set([item.row() for item in self.selectedItems()]))
            self._rows_deleted_event(rows)

        self._delete_row_action.triggered.connect(on_delete_rows)
        self.addAction(self._delete_row_action)

    def _rows_deleted_event(self, rows: List[int]) -> None:
        """IMPLEMENT ME. Called when the user does a delete action."""
        pass

    def _populate_context_menu(self, menu: QMenu) -> None:
        super()._populate_context_menu(menu)
        menu.addAction(self._delete_row_action)


class SignalRemovalXyPlotTable(DeleteableXyPlotTable):
    """Provides a removal function to remove an XY"""

    def _rows_deleted_event(self, rows: List[int]) -> None:
        super()._rows_deleted_event(rows)
        for row in reversed(sorted(rows)):
            if row < len(self._xy_plots._xys):
                self._xy_plots.remove_xy(*self._xy_plots._xys[row])
