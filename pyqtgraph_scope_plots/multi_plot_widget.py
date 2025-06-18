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
from typing import Dict, Tuple, List, Optional, Any, Callable, Union, Mapping, cast, Literal

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg
from PySide6.QtCore import QSignalBlocker, QPoint, QSize, Signal
from PySide6.QtGui import QColor, Qt, QDropEvent, QDragLeaveEvent, QPainter, QBrush, QDragMoveEvent, QPaintEvent
from PySide6.QtWidgets import QWidget, QSplitter
from pydantic import BaseModel

from .enum_waveform_plotitem import EnumWaveformPlot
from .interactivity_mixins import PointsOfInterestPlot, RegionPlot, LiveCursorPlot, DraggableCursorPlot
from .util import BaseTopModel, HasSaveLoadDataConfig


class InteractivePlot(DraggableCursorPlot, PointsOfInterestPlot, RegionPlot, LiveCursorPlot):
    """PlotItem with interactivity mixins"""


class EnumWaveformInteractivePlot(
    DraggableCursorPlot, PointsOfInterestPlot, RegionPlot, LiveCursorPlot, EnumWaveformPlot
):
    """Enum plot with all the interactivity mixins"""

    LIVE_CURSOR_X_ANCHOR = (1, 0.5)
    LIVE_CURSOR_Y_ANCHOR = (0, 0.5)
    POI_ANCHOR = (0, 0.5)


class PlotWidgetModel(BaseModel):
    data_items: List[str] = []  # window index -> list of data items
    y_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None


class MultiPlotStateModel(BaseTopModel):
    plot_widgets: Optional[List[PlotWidgetModel]] = None  # window index -> list of data items
    x_range: Optional[Union[Tuple[float, float], Literal["auto"]]] = None


class MultiPlotWidget(HasSaveLoadDataConfig, QSplitter):
    """A splitter that can contain multiple (vertically stacked) plots with linked x-axis"""

    class PlotType(Enum):
        DEFAULT = 0  # x-y plot
        ENUM_WAVEFORM = 1  # renders string-valued enums as a waveform

    class NewDataAction(Enum):
        NEW_PLOT = 0  # creates a new plot window for each new data
        MERGE_LAST = 1  # appends new data to the last plot window

    # TODO belongs in LinkedMultiPlotWidget, but signals break with multiple inheritance
    sigHoverCursorChanged = Signal(object)  # Optional[float] = x-position
    sigCursorRangeChanged = Signal(object)  # Optional[Union[float, Tuple[float, float]]] as cursor / region
    sigPoiChanged = Signal(object)  # List[float] as current POIs
    sigDragCursorChanged = Signal(float)  # x-position
    sigDragCursorCleared = Signal()

    sigDataItemsUpdated = Signal()  # called when new plot data items are set
    sigDataUpdated = Signal()  # called when new plot data is available

    _MODEL_BASES = [MultiPlotStateModel]

    def __init__(
        self,
        *args: Any,
        x_axis: Optional[Callable[[], pg.AxisItem]] = None,
        new_data_action: NewDataAction = NewDataAction.NEW_PLOT,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._x_axis_fn = x_axis
        self._new_data_action = new_data_action

        self._data_items: Mapping[str, Tuple[QColor, MultiPlotWidget.PlotType]] = {}  # ordered
        self._raw_data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]] = {}  # pre-transforms, immutable
        self._data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]] = {}  # post-transforms

        self._data_curves: Dict[str, List[pg.PlotCurveItem]] = {}

        self.setOrientation(Qt.Orientation.Vertical)
        default_plot_item = self._init_plot_item(self._create_plot_item(self.PlotType.DEFAULT))
        default_plot_widget = pg.PlotWidget(plotItem=default_plot_item)
        self.addWidget(default_plot_widget)
        # contained data items per plot
        self._plot_item_data: Dict[pg.PlotItem, List[Optional[str]]] = {default_plot_item: []}
        # re-derived when _plot_item_data updated
        self._data_name_to_plot_item: Dict[Optional[str], pg.PlotItem] = {None: default_plot_item}
        self._anchor_x_plot_item: pg.PlotItem = default_plot_item  # PlotItem that everyone's x-axis is linked to

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, MultiPlotStateModel)
        model.plot_widgets = []
        x_viewbox: Optional[pg.ViewBox] = None

        for i in range(self.count()):
            widget = self.widget(i)
            if not isinstance(widget, pg.PlotWidget):  # ignored
                continue
            widget_model = PlotWidgetModel()
            widget_model.data_items = [
                data_item for data_item in self._plot_item_data.get(widget.getPlotItem(), []) if data_item is not None
            ]
            widget_viewbox = cast(pg.PlotItem, widget.getPlotItem()).getViewBox()
            if widget_viewbox.autoRangeEnabled()[1]:
                widget_model.y_range = "auto"
            else:
                widget_model.y_range = tuple(widget_viewbox.viewRange()[1])
            model.plot_widgets.append(widget_model)

            if x_viewbox is None:
                x_viewbox = widget_viewbox

        if x_viewbox is not None:
            if x_viewbox.autoRangeEnabled()[0]:
                model.x_range = "auto"
            else:
                model.x_range = tuple(x_viewbox.viewRange()[0])

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)

        assert isinstance(model, MultiPlotStateModel)
        if model.plot_widgets is None:
            return

        self._plot_item_data = {}  # remove all existing plots

        for plot_widget_model in model.plot_widgets:  # create plots from model
            if len(plot_widget_model.data_items) < 1:  # skip empty plots
                continue
            color, plot_type = self._data_items.get(plot_widget_model.data_items[0], (None, None))
            if plot_type is None:
                continue
            add_plot_item = self._init_plot_item(self._create_plot_item(plot_type))
            plot_widget = pg.PlotWidget(plotItem=add_plot_item)
            self.addWidget(plot_widget)
            self._plot_item_data[add_plot_item] = plot_widget_model.data_items  # type: ignore

            widget_viewbox = cast(pg.PlotItem, plot_widget.getPlotItem()).getViewBox()
            if model.x_range is not None and model.x_range != "auto":
                widget_viewbox.setXRange(model.x_range[0], model.x_range[1], 0)
            if plot_widget_model.y_range is not None and plot_widget_model.y_range != "auto":
                widget_viewbox.setYRange(plot_widget_model.y_range[0], plot_widget_model.y_range[1], 0)
            if model.x_range == "auto" or plot_widget_model.y_range == "auto":
                widget_viewbox.enableAutoRange(
                    x=model.x_range == "auto" or None, y=plot_widget_model.y_range == "auto" or None
                )

        self._clean_plot_widgets()
        self._check_create_default_plot()
        self._update_plots_x_axis()
        self._update_data_name_to_plot_item()

    def render_value(self, data_name: str, value: float) -> str:
        """Float-to-string conversion for a value. Optionally override this to provide smarter precision."""
        plot_item = self._data_name_to_plot_item.get(data_name, None)
        if plot_item is None:
            return f"{value:.3f}"
        return LiveCursorPlot._value_axis_label(value, plot_item, "left", precision_factor=0.1)

    def view_x_range(self) -> Tuple[float, float]:
        """Returns the current x view range"""
        return self._anchor_x_plot_item.viewRect().left(), self._anchor_x_plot_item.viewRect().right()

    def set_x_axis(self, x_axis: Callable[[], pg.AxisItem]) -> None:
        """Sets the X axis of plots, updating existing plots and for future plots.
        The axis must be given as a function, to return a fresh axis for each plot."""
        self._x_axis_fn = x_axis
        for i in range(self.count()):
            widget = self.widget(i)
            if not isinstance(widget, pg.PlotWidget):
                continue
            widget.setAxisItems({"bottom": self._x_axis_fn()})
        self._update_plots_x_axis()

    def _update_data_name_to_plot_item(self) -> None:
        """Creates the data name to plot item dict."""
        self._data_name_to_plot_item = {}
        for plot_item, data_names in self._plot_item_data.items():
            for name in data_names:
                self._data_name_to_plot_item[name] = plot_item

    def _create_plot_item(self, plot_type: "MultiPlotWidget.PlotType") -> pg.PlotItem:
        """Given a PlotType, creates the PlotItem and returns it. Override to change the instantiated PlotItem type."""
        plot_args = {}
        if self._x_axis_fn is not None:
            plot_args["axisItems"] = {"bottom": self._x_axis_fn()}
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
        self, new_data_items: List[Tuple[str, QColor, "MultiPlotWidget.PlotType"]], *, no_create: bool = False
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

        # add new plots based on the requested action
        if not no_create:
            for data_name, color, plot_type in new_data_items:
                if data_name in self._data_items.keys():  # already exists
                    continue
                add_plot_item: Optional[pg.PlotItem] = None

                if self._new_data_action == self.NewDataAction.MERGE_LAST and plot_type != self.PlotType.ENUM_WAVEFORM:
                    # if merging plots, try to get the plot to merge into
                    for i in reversed(range(self.count())):
                        widget = self.widget(i)
                        if not isinstance(widget, pg.PlotWidget):
                            continue
                        test_plot_item = widget.getPlotItem()
                        if isinstance(test_plot_item, EnumWaveformInteractivePlot):  # skip enum plots, can't merge
                            continue
                        if test_plot_item not in self._plot_item_data:  # ignore removed (deleteLater'd) plots
                            continue
                        add_plot_item = test_plot_item
                        break

                if add_plot_item is None:  # create a new plot if needed
                    add_plot_item = self._init_plot_item(self._create_plot_item(plot_type))
                    if self._anchor_x_plot_item is not None:
                        add_plot_item.setXLink(self._anchor_x_plot_item)
                    else:
                        self._anchor_x_plot_item = add_plot_item
                    plot_widget = pg.PlotWidget(plotItem=add_plot_item)
                    self.addWidget(plot_widget)

                self._plot_item_data.setdefault(add_plot_item, []).append(data_name)

        self._data_items = {name: (color, plot_type) for name, color, plot_type in new_data_items}

        self._check_create_default_plot()
        self._update_data_name_to_plot_item()
        self._update_plots_x_axis()
        self.sigDataItemsUpdated.emit()

    def _to_array(self, x: npt.ArrayLike) -> npt.NDArray:
        if isinstance(x, np.ndarray) and x.flags.writeable == False:
            return x
        else:
            arr = np.array(x)
            arr.flags.writeable = False
            return arr

    def _transform_data(
        self, data: Mapping[str, Tuple[npt.NDArray, npt.NDArray]]
    ) -> Mapping[str, Tuple[npt.NDArray, npt.NDArray]]:
        """Optional function to transform data between the input of set_data and when it is plotted.
        Data is guaranteed to be a numpy array"""
        return data

    def set_data(self, data: Mapping[str, Tuple[np.typing.ArrayLike, np.typing.ArrayLike]]) -> None:
        """Sets the data to be plotted as data name -> (xs, ys). Data names must have been previously set with
        set_data_items, missing items will log an error."""
        self._raw_data = {name: (self._to_array(xs), self._to_array(ys)) for name, (xs, ys) in data.items()}
        self._update_plots()
        self.sigDataUpdated.emit()

    def _update_plots(self) -> None:
        self._data_curves = {}
        self._data = self._transform_data(self._raw_data)
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
                    assert isinstance(data_name, str)
                    color = self._data_items.get(data_name, (QColor("black"), None))[0]
                    xs, ys = self._data.get(data_name, ([], []))
                    curve = pg.PlotCurveItem(x=xs, y=ys, name=data_name)
                    curve.setPen(color=color, width=1)
                    plot_item.addItem(curve)
                    self._data_curves.setdefault(data_name, []).append(curve)

    def autorange(self, enable: bool) -> None:
        is_first = True
        for plot_item, _ in self._plot_item_data.items():
            if is_first:
                plot_item.enableAutoRange(enable=enable)  # only range X axis on one to avoid fighting
                is_first = False
            else:
                plot_item.enableAutoRange(axis="y", enable=enable)


class LinkedMultiPlotStateModel(BaseTopModel):
    region: Optional[Union[Tuple[()], float, Tuple[float, float]]] = None
    pois: Optional[List[float]] = None


class LinkedMultiPlotWidget(MultiPlotWidget, HasSaveLoadDataConfig):
    """Mixin into the MultiPlotWidget that links PointsOfInterestPlot, RegionPlot, and LiveCursorPlot"""

    _MODEL_BASES = [LinkedMultiPlotStateModel]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._last_hover: Optional[float] = None  # must be init'd before the first plot is created in __init__
        self._last_region: Optional[Union[float, Tuple[float, float]]] = None
        self._last_pois: List[float] = []
        self._last_drag_cursor: Optional[float] = None
        super().__init__(*args, **kwargs)

    def _write_model(self, model: BaseModel) -> None:
        super()._write_model(model)
        assert isinstance(model, LinkedMultiPlotStateModel)
        model.region = self._last_region
        model.pois = self._last_pois

    def _load_model(self, model: BaseModel) -> None:
        super()._load_model(model)
        assert isinstance(model, LinkedMultiPlotStateModel)
        if model.region is not None:
            region = model.region
            if region == ():  # convert empty model format to internal region format
                self._on_region_change(None, None)
            else:
                self._on_region_change(None, region)  # type: ignore
        if model.pois is not None:
            self._on_poi_change(None, model.pois)

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

    def _on_hover_cursor_change(self, sig_plot_item: Optional[pg.PlotItem], position: Optional[float]) -> None:
        """Propagates cursor change to all plots, excluding signal source sig_plot_item if specified."""
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, LiveCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_live_cursor(position)
        self._last_hover = position
        self.sigHoverCursorChanged.emit(position)

    def _on_region_change(
        self, sig_plot_item: Optional[pg.PlotItem], region: Optional[Union[float, Tuple[float, float]]]
    ) -> None:
        """Propagates region change to all plots, excluding signal source sig_plot_item if specified."""
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, RegionPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_region(region)
        self._last_region = region
        self.sigCursorRangeChanged.emit(region)

    def _on_poi_change(self, sig_plot_item: Optional[pg.PlotItem], pois: List[float]) -> None:
        """Propagates POI change to all plots, excluding signal source sig_plot_item if specified."""
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, PointsOfInterestPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_pois(pois)
        self._last_pois = pois
        self.sigPoiChanged.emit(pois)

    def create_drag_cursor(self, pos: float) -> None:
        for plot_item, _ in self._plot_item_data.items():
            if isinstance(plot_item, DraggableCursorPlot):
                plot_item.set_drag_cursor(pos)
        self._last_drag_cursor = pos

    def _on_drag_cursor_change(self, sig_plot_item: pg.PlotItem, pos: float) -> None:
        """Propagates drag cursor to all plots, excluding signal source sig_plot_item if specified."""
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, DraggableCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_drag_cursor(pos)
        self._last_drag_cursor = pos
        self.sigDragCursorChanged.emit(pos)

    def _on_drag_cursor_clear(self, sig_plot_item: pg.PlotItem) -> None:
        """Propagates drag cursor removal to all plots, excluding signal source sig_plot_item if specified."""
        for plot_item, _ in self._plot_item_data.items():
            if plot_item is not sig_plot_item and isinstance(plot_item, DraggableCursorPlot):
                with QSignalBlocker(plot_item):
                    plot_item.set_drag_cursor(None)
        self._last_drag_cursor = None
        self.sigDragCursorCleared.emit()


class DragTargetOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        # these prevent overlay flickering when the overlay intercepts the drag
        # and cancels the underlying widget's drag
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

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

    def _merge_data_into_item(self, source_data_names: List[str], target_plot_index: int, insert: bool = False) -> None:
        """Merges a data (by name) into a target PlotItem, overlaying both on the same plot"""
        if len(source_data_names) == 0:  # notihng to be done
            return

        created_data_names = []  # list of data names that were successfully created / moved
        if not insert:  # merge mode
            target_plot_widget = self.widget(target_plot_index)
            if not isinstance(target_plot_widget, pg.PlotWidget):
                return
            target_plot_item = target_plot_widget.getPlotItem()
            if isinstance(target_plot_item, EnumWaveformPlot):  # can't merge into enum plots
                return
            for source_data_name in source_data_names:
                if len(self._plot_item_data[target_plot_item]) > 0:  # check for merge-ability, for nonempty plots
                    if (
                        self._data_items[self._plot_item_data[target_plot_item][0] or ""][1]
                        != self._data_items[source_data_name][1]
                    ):
                        continue
                self._plot_item_data[target_plot_item].append(source_data_name)
                created_data_names.append(source_data_name)
        else:  # create-new-graph-and-insert mode
            plot_item = self._init_plot_item(self._create_plot_item(self._data_items[source_data_names[0]][1]))
            if self._anchor_x_plot_item is not None:
                plot_item.setXLink(self._anchor_x_plot_item)
            else:
                self._anchor_x_plot_item = plot_item
            plot_widget = pg.PlotWidget(plotItem=plot_item)
            self.insertWidget(target_plot_index, plot_widget)

            self._plot_item_data[plot_item] = [source_data_names[0]]
            created_data_names.append(source_data_names[0])

            if isinstance(plot_item, EnumWaveformPlot):  # only one data item
                pass
            else:  # append all compatible
                for source_data_name in source_data_names[1:]:
                    if self._data_items[source_data_names[0]][1] != self._data_items[source_data_name][1]:
                        continue
                    self._plot_item_data[plot_item].append(source_data_name)
                    created_data_names.append(source_data_name)

            self._update_plots_x_axis()

        for created_data_name in created_data_names:
            created_item = self._data_name_to_plot_item.get(created_data_name)
            if created_item is not None:  # delete source
                self._plot_item_data[created_item].remove(created_data_name)
                if not len(self._plot_item_data[created_item]):
                    self._clean_plot_widgets()
                    self._update_plots_x_axis()

        self._update_data_name_to_plot_item()
        self._update_plots()

    def dragEnterEvent(self, event: QDragMoveEvent) -> None:
        from .signals_table import DraggableSignalsTable

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
                    top_overlay.move(QPoint(0, target_widget.height() - self.DRAG_INSERT_TARGET_SIZE))
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
            self._drag_overlays[0].move(QPoint(0, last_plot_index_widget[1].height() - self.DRAG_INSERT_TARGET_SIZE))
            self._drag_overlays[0].resize(QSize(last_plot_index_widget[1].width(), self.DRAG_INSERT_TARGET_SIZE))
            self._drag_overlays[0].setVisible(True)
            self._drag_target = (last_plot_index_widget[0] + 1, True)
            event.accept()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._clear_drag_overlays()

    def dropEvent(self, event: QDropEvent) -> None:
        from .signals_table import DraggableSignalsTable

        self._clear_drag_overlays()

        data = event.mimeData().data(DraggableSignalsTable.DRAG_MIME_TYPE)
        if not data or self._drag_target is None:
            return
        drag_data_names = bytes(data.data()).decode("utf-8").split("\0")

        target_index, target_insertion = self._drag_target
        self._merge_data_into_item(drag_data_names, target_index, target_insertion)
        self._drag_target = None
        event.accept()
