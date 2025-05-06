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

from enum import Enum
from functools import partial
from typing import (
    Dict,
    Tuple,
    List,
    Optional,
    Any,
    Callable,
    Union,
    Mapping,
    cast,
)

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg
from PySide6.QtCore import QSignalBlocker, QPoint, QSize, Signal
from PySide6.QtGui import (
    QColor,
    Qt,
    QDropEvent,
    QDragLeaveEvent,
    QPainter,
    QBrush,
    QDragMoveEvent,
    QPaintEvent,
)
from PySide6.QtWidgets import QWidget, QSplitter

from .enum_waveform_plotitem import EnumWaveformPlot
from .interactivity_mixins import (
    PointsOfInterestPlot,
    RegionPlot,
    LiveCursorPlot,
    DraggableCursorPlot,
)
from .signals_table import DraggableSignalsTable


class InteractivePlot(DraggableCursorPlot, PointsOfInterestPlot, RegionPlot, LiveCursorPlot):
    """PlotItem with interactivity mixins"""


class EnumWaveformInteractivePlot(
    DraggableCursorPlot,
    PointsOfInterestPlot,
    RegionPlot,
    LiveCursorPlot,
    EnumWaveformPlot,
):
    """Enum plot with all the interactivity mixins"""

    LIVE_CURSOR_X_ANCHOR = (1, 0.5)
    LIVE_CURSOR_Y_ANCHOR = (0, 0.5)
    POI_ANCHOR = (0, 0.5)


class MultiPlotWidget(QSplitter):
    """A splitter that can contain multiple (vertically stacked) plots with linked x-axis"""

    class PlotType(Enum):
        DEFAULT = 0  # x-y plot
        ENUM_WAVEFORM = 1  # renders string-valued enums as a waveform

    # TODO belongs in LinkedMultiPlotWidget, but signals break with multiple inheritance
    sigHoverCursorChanged = Signal(object)  # Optional[float] = x-position
    sigCursorRangeChanged = Signal(object)  # Optional[Union[float, Tuple[float, float]]] as cursor / region
    sigPoiChanged = Signal(object)  # List[float] as current POIs
    sigDragCursorChanged = Signal(float)  # x-position
    sigDragCursorCleared = Signal()

    def __init__(
        self,
        *args: Any,
        x_axis: Optional[Callable[[], pg.AxisItem]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._x_axis = x_axis

        self._data_items: Mapping[str, Tuple[QColor, MultiPlotWidget.PlotType]] = {}  # ordered
        self._data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = {}

        self.setOrientation(Qt.Orientation.Vertical)
        default_plot_item = self._init_plot_item(self._create_plot_item(self.PlotType.DEFAULT))
        default_plot_widget = pg.PlotWidget(plotItem=default_plot_item)
        self.addWidget(default_plot_widget)
        # contained data items per plot
        self._plot_item_data: Dict[pg.PlotItem, List[Optional[str]]] = {default_plot_item: []}
        # re-derived when _plot_item_data updated
        self._data_name_to_plot_item: Dict[Optional[str], pg.PlotItem] = {None: default_plot_item}
        self._anchor_x_plot_item: pg.PlotItem = default_plot_item  # PlotItem that everyone's x-axis is linked to

    def render_value(self, data_name: str, value: float) -> str:
        """Float-to-string conversion for a value. Optionally override this to provide smarter precision."""
        plot_item = self._data_name_to_plot_item.get(data_name, None)
        if plot_item is None:
            return f"{value:.3f}"
        return LiveCursorPlot._value_axis_label(value, plot_item, "left", precision_factor=0.1)

    def view_x_range(self) -> Tuple[float, float]:
        """Returns the current x view range"""
        return (
            self._anchor_x_plot_item.viewRect().left(),
            self._anchor_x_plot_item.viewRect().right(),
        )

    def _update_data_name_to_plot_item(self) -> None:
        """Creates the data name to plot item dict."""
        self._data_name_to_plot_item = {}
        for plot_item, data_names in self._plot_item_data.items():
            for name in data_names:
                self._data_name_to_plot_item[name] = plot_item

    def _create_plot_item(self, plot_type: "MultiPlotWidget.PlotType") -> pg.PlotItem:
        """Given a PlotType, creates the PlotItem and returns it. Override to change the instantiated PlotItem type."""
        plot_args = {}
        if self._x_axis is not None:
            plot_args["axisItems"] = {"bottom": self._x_axis()}
        if plot_type == self.PlotType.DEFAULT:
            return InteractivePlot(**plot_args)
        elif plot_type == self.PlotType.ENUM_WAVEFORM:
            return EnumWaveformInteractivePlot(**plot_args)
        else:
            raise ValueError(f"unknown plot_type {plot_type}")

    def _init_plot_item(self, plot_item: pg.PlotItem) -> pg.PlotItem:
        """Called after _create_plot_item, does any post-creation init. Returns the same plot_item.
        Optionally override this with a super() call."""
        return plot_item

    def _clean_plot_widgets(self) -> None:
        """Called when plot items potentially have been emptied / deleted, to clean things up"""
        for i in range(self.count()):
            widget = self.widget(i)
            if not isinstance(widget, pg.PlotWidget):
                continue
            if widget.getPlotItem() not in self._plot_item_data or not len(self._plot_item_data[widget.getPlotItem()]):
                if widget.getPlotItem() is self._anchor_x_plot_item:  # about to delete the x-axis anchor
                    self._anchor_x_plot_item = None
                if widget.getPlotItem() in self._plot_item_data:
                    del self._plot_item_data[widget.getPlotItem()]
                widget.deleteLater()

        if self._anchor_x_plot_item is None:  # select a new x-axis anchor and re-link
            for plot_item, _ in self._plot_item_data.items():
                if self._anchor_x_plot_item is None:
                    self._anchor_x_plot_item = plot_item
                else:
                    plot_item.setXLink(self._anchor_x_plot_item)

    def _update_plots_x_axis(self) -> None:
        """Updates plots so only last plot's x axis labels and ticks are visible"""
        is_first = True
        for i in reversed(range(self.count())):
            widget = self.widget(i)
            if not isinstance(widget, pg.PlotWidget):
                continue
            plot_item = widget.getPlotItem()
            if plot_item not in self._plot_item_data:  # ignores removed (deleteLater'd) plots
                continue
            bottom_axis = cast(pg.AxisItem, plot_item.getAxis("bottom"))
            bottom_axis.setStyle(showValues=is_first)
            bottom_axis.showLabel(is_first)
            if isinstance(plot_item, RegionPlot):  # TODO should this be part of a different mixin?
                plot_item.show_cursor_range_labels = is_first
                with QSignalBlocker(plot_item):
                    plot_item._update_cursor_labels()

            if is_first:
                is_first = False

    def _check_create_default_plot(self) -> None:
        """Ensure there is always a plot on th screen. If there are no plots visible, create a default empty one."""
        if not self._plot_item_data:
            plot_item = self._init_plot_item(self._create_plot_item(self.PlotType.DEFAULT))
            plot_widget = pg.PlotWidget(plotItem=plot_item)
            self.addWidget(plot_widget)
            self._plot_item_data[plot_item] = []
            self._anchor_x_plot_item = plot_item

    def remove_plot_items(self, remove_data_names: List[str]) -> None:
        for plot_item, data_names in self._plot_item_data.items():
            self._plot_item_data[plot_item] = list(filter(lambda x: x not in remove_data_names, data_names))

        self._clean_plot_widgets()
        self._check_create_default_plot()
        self._update_plots_x_axis()
        self._update_data_name_to_plot_item()
        self._update_plots()

    def show_data_items(
        self,
        new_data_items: List[Tuple[str, QColor, "MultiPlotWidget.PlotType"]],
        *,
        no_create: bool = False,
    ) -> None:
        """Updates the data items shown, as ordered pairs of data name, color.
        This adds / deletes plots instead of re-creating, to preserve any user combining of plots.
        If no_create is true, no new plots will be created - useful when loading large data traces.
        Data names are keyed by name, duplicate entries are dropped."""
        new_data_names = [name for name, _, _ in new_data_items]

        # remove plots not in new_data_items
        for plot_item, data_names in self._plot_item_data.items():
            self._plot_item_data[plot_item] = list(filter(lambda x: x in new_data_names, data_names))
        self._clean_plot_widgets()

        # add new plots as new widgets
        if not no_create:
            for data_name, color, plot_type in new_data_items:
                if data_name in self._data_items.keys():
                    continue
                plot_item = self._init_plot_item(self._create_plot_item(plot_type))
                if self._anchor_x_plot_item is not None:
                    plot_item.setXLink(self._anchor_x_plot_item)
                else:
                    self._anchor_x_plot_item = plot_item
                plot_widget = pg.PlotWidget(plotItem=plot_item)
                self.addWidget(plot_widget)
                self._plot_item_data[plot_item] = [data_name]

        self._data_items = {name: (color, plot_type) for name, color, plot_type in new_data_items}

        self._check_create_default_plot()
        self._update_data_name_to_plot_item()
        self._update_plots_x_axis()

    def set_data(
        self,
        data: Mapping[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]],
    ) -> None:
        """Sets the data to be plotted as data name -> (xs, ys). Data names must have been previously set with
        set_data_items, missing items will log an error."""
        self._data = {name: (np.array(xs), np.array(ys)) for name, (xs, ys) in data.items()}
        self._update_plots()

    def _update_plots(self) -> None:
        for plot_item, data_names in self._plot_item_data.items():
            if isinstance(plot_item, EnumWaveformPlot):  # TODO: enum plots have a different API, this should be unified
                data_name = data_names[0]
                color = self._data_items.get(cast(str, data_name), (QColor("black"), None))[0]
                xs, ys = self._data.get(
                    cast(str, data_name), ([], [])
                )  # None is valid for dict.get, cast to satisfy typer
                plot_item.update_plot(data_name or "", color, xs, ys)
            else:
                for data_item in plot_item.listDataItems():  # clear existing
                    plot_item.removeItem(data_item)
                for data_name in data_names:
                    color = self._data_items.get(cast(str, data_name), (QColor("black"), None))[0]
                    xs, ys = self._data.get(cast(str, data_name), ([], []))
                    curve = pg.PlotCurveItem(x=xs, y=ys, name=data_name)
                    curve.setPen(color=color, width=1)
                    plot_item.addItem(curve)

    def autorange(self, enable: bool) -> None:
        is_first = True
        for plot_item, _ in self._plot_item_data.items():
            if is_first:
                plot_item.enableAutoRange(enable=enable)  # only range X axis on one to avoid fighting
                is_first = False
            else:
                plot_item.enableAutoRange(axis="y", enable=enable)


class LinkedMultiPlotWidget(MultiPlotWidget):
    """Mixin into the MultiPlotWidget that links PointsOfInterestPlot, RegionPlot, and LiveCursorPlot"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._last_hover: Optional[float] = None  # must be init'd before the first plot is created in __init__
        self._last_region: Optional[Union[float, Tuple[float, float]]] = None
        self._last_pois: List[float] = []
        self._last_drag_cursor: Optional[float] = None
        super().__init__(*args, **kwargs)

    def _init_plot_item(self, plot_item: pg.PlotItem) -> pg.PlotItem:
        """Called after _create_plot_item, does any post-creation init. Returns the same plot_item."""
        plot_item = super()._init_plot_item(plot_item)
        if isinstance(plot_item, LiveCursorPlot):
            plot_item.set_live_cursor(self._last_hover)
            plot_item.sigHoverCursorChanged.connect(partial(self._on_hover_cursor_change, plot_item))
        if isinstance(plot_item, RegionPlot):
            plot_item.set_region(self._last_region)
            plot_item.sigCursorRangeChanged.connect(partial(self._on_region_change, plot_item))
        if isinstance(plot_item, PointsOfInterestPlot):
            plot_item.set_pois(self._last_pois)
            plot_item.sigPoiChanged.connect(partial(self._on_poi_change, plot_item))
        if isinstance(plot_item, DraggableCursorPlot):
            plot_item.set_drag_cursor(self._last_drag_cursor)
            plot_item.sigDragCursorChanged.connect(partial(self._on_drag_cursor_change, plot_item))
            plot_item.sigDragCursorCleared.connect(partial(self._on_drag_cursor_clear, plot_item))
        return plot_item

    def _on_hover_cursor_change(self, sig_plot_item: pg.PlotItem, position: Optional[float]) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, LiveCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_live_cursor(position)
        self.sigHoverCursorChanged.emit(position)
        self._last_hover = position

    def _on_region_change(
        self,
        sig_plot_item: pg.PlotItem,
        region: Optional[Union[float, Tuple[float, float]]],
    ) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, RegionPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_region(region)
        self.sigCursorRangeChanged.emit(region)
        self._last_region = region

    def _on_poi_change(self, sig_plot_item: pg.PlotItem, pois: List[float]) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, PointsOfInterestPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_pois(pois)
        self.sigPoiChanged.emit(pois)
        self._last_pois = pois

    def create_drag_cursor(self, pos: float) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if isinstance(plot_item, DraggableCursorPlot):
                plot_item.set_drag_cursor(pos)
        self._last_drag_cursor = pos

    def _on_drag_cursor_change(self, sig_plot_item: pg.PlotItem, pos: float) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, DraggableCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_drag_cursor(pos)
        self.sigDragCursorChanged.emit(pos)
        self._last_drag_cursor = pos

    def _on_drag_cursor_clear(self, sig_plot_item: pg.PlotItem) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, DraggableCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_drag_cursor(None)
        self.sigDragCursorCleared.emit()
        self._last_drag_cursor = None


class DragTargetOverlay(QWidget):
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter()
        painter.begin(self)
        painter.fillRect(event.rect(), QBrush(QColor(255, 255, 255, 63)))


class DroppableMultiPlotWidget(MultiPlotWidget):
    """Mixin into the MultiPlotWidget that allows (externally-initiated) drag'n'drop to reorder and merge graphs"""

    DRAG_INSERT_TARGET_SIZE = 10  # px, height of overlay and drag target for insertion-between-plots

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._drag_target: Optional[Tuple[int, bool]] = None  # insertion index, insertion (True) or overlay (False)
        self._drag_overlays: List[DragTargetOverlay] = []
        self.setAcceptDrops(True)

    def _merge_data_into_item(
        self,
        source_data_name: str,
        target_plot_index: int,
        insert: bool = False,
    ) -> None:
        """Merges a data (by name) into a target PlotItem, overlaying both on the same plot"""
        source_item = self._data_name_to_plot_item.get(source_data_name)
        if not insert:  # merge mode
            target_plot_widget = self.widget(target_plot_index)
            if not isinstance(target_plot_widget, pg.PlotWidget):
                return
            target_plot_item = target_plot_widget.getPlotItem()
            if isinstance(target_plot_item, EnumWaveformPlot):  # can't merge into enum plots
                return
            if (
                len(self._plot_item_data[target_plot_item]) > 0
                and self._data_items[self._plot_item_data[target_plot_item][0] or ""][1]
                != self._data_items[source_data_name][1]
            ):
                return  # can't merge different plot types
            self._plot_item_data[target_plot_item].append(source_data_name)
        else:  # create-new-graph-and-insert mode
            plot_item = self._init_plot_item(self._create_plot_item(self._data_items[source_data_name][1]))
            if self._anchor_x_plot_item is not None:
                plot_item.setXLink(self._anchor_x_plot_item)
            else:
                self._anchor_x_plot_item = plot_item
            plot_widget = pg.PlotWidget(plotItem=plot_item)
            self.insertWidget(target_plot_index, plot_widget)
            self._plot_item_data[plot_item] = [source_data_name]
            self._update_plots_x_axis()

        if source_item is not None:  # delete source
            self._plot_item_data[source_item].remove(source_data_name)
            if not len(self._plot_item_data[source_item]):
                self._clean_plot_widgets()
                self._update_plots_x_axis()

        self._update_data_name_to_plot_item()
        self._update_plots()

    def dragEnterEvent(self, event: QDragMoveEvent) -> None:
        if not event.mimeData().data(DraggableSignalsTable.DRAG_MIME_TYPE):  # check for right type
            return
        event.accept()

    def _clear_drag_overlays(self) -> None:
        for drag_overlay in self._drag_overlays:
            drag_overlay.deleteLater()
        self._drag_overlays = []

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        self._clear_drag_overlays()
        self._drag_target = None

        last_plot_index_widget: Optional[Tuple[int, pg.PlotWidget]] = None
        for i in range(self.count()):  # test y positions including between plots
            target_widget = self.widget(i)
            if not isinstance(target_widget, pg.PlotWidget):
                continue
            target_top_left = target_widget.mapToParent(QPoint(0, 0))
            target_bot_right = target_widget.mapToParent(QPoint(0, target_widget.size().height()))

            if event.pos().y() < target_top_left.y() + self.DRAG_INSERT_TARGET_SIZE:  # was part of above plot
                if last_plot_index_widget is not None:  # has a widget above
                    top_overlay = DragTargetOverlay(last_plot_index_widget[1])
                    top_overlay.move(
                        QPoint(
                            0,
                            target_widget.height() - self.DRAG_INSERT_TARGET_SIZE,
                        )
                    )
                    top_overlay.resize(QSize(target_widget.width(), self.DRAG_INSERT_TARGET_SIZE))
                    top_overlay.setVisible(True)
                    self._drag_overlays.append(top_overlay)
                this_overlay = DragTargetOverlay(target_widget)
                this_overlay.resize(QSize(target_widget.width(), self.DRAG_INSERT_TARGET_SIZE))
                this_overlay.setVisible(True)
                self._drag_overlays.append(this_overlay)
                self._drag_target = (i, True)
                event.accept()
                return
            elif event.pos().y() <= target_bot_right.y() - self.DRAG_INSERT_TARGET_SIZE:  # in this current plot
                self._drag_overlays = [DragTargetOverlay(target_widget)]
                self._drag_overlays[0].resize(target_widget.size())
                self._drag_overlays[0].setVisible(True)
                self._drag_target = (i, False)
                event.accept()
                return

            last_plot_index_widget = i, target_widget

        if last_plot_index_widget is not None:  # reached the end, append after last plot
            self._drag_overlays = [DragTargetOverlay(last_plot_index_widget[1])]
            self._drag_overlays[0].move(
                QPoint(
                    0,
                    last_plot_index_widget[1].height() - self.DRAG_INSERT_TARGET_SIZE,
                )
            )
            self._drag_overlays[0].resize(
                QSize(
                    last_plot_index_widget[1].width(),
                    self.DRAG_INSERT_TARGET_SIZE,
                )
            )
            self._drag_overlays[0].setVisible(True)
            self._drag_target = (last_plot_index_widget[0] + 1, True)
            event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._clear_drag_overlays()

    def dropEvent(self, event: QDropEvent) -> None:
        self._clear_drag_overlays()

        data = event.mimeData().data(DraggableSignalsTable.DRAG_MIME_TYPE)
        if not data or self._drag_target is None:
            return
        drag_data_name = bytes(data.data()).decode("utf-8")

        target_index, target_insertion = self._drag_target
        self._merge_data_into_item(drag_data_name, target_index, target_insertion)
        self._drag_target = None
        event.accept()
