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

"""
Mixins into pyqtgraph PlotItem that provide interactivity functionality, including snap-to-cursor,
live x-axis cursor, region selection, and points-of-interest.
"""

import bisect
from abc import abstractmethod
from typing import List, Tuple, Dict, Optional, Any, cast, NamedTuple, Union, Mapping

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QSignalBlocker, Signal, Slot
from PySide6.QtGui import Qt, QColor, QKeyEvent
from PySide6.QtWidgets import QGraphicsSceneMouseEvent
from numpy import typing as npt
from pyqtgraph import mkPen
from pyqtgraph.GraphicsScene.mouseEvents import HoverEvent

from pyqtgraph_scope_plots.graphics_collections import ScatterItemCollection, TextItemCollection


class DataPlotItem(pg.PlotItem):  # type: ignore[misc]
    """Abstract base class for a PlotItem that takes some data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._data_items: Dict[str, QColor] = {}
        self._data_graphics: Dict[str, List[pg.GraphicsObject]] = {}
        self._data: Dict[str, Tuple[npt.NDArray[np.float64], npt.NDArray]] = {}

    def set_data_items(self, data_items: Mapping[str, QColor]) -> None:
        """Generates plot items for the input data items."""
        for graphics in self._data_graphics.values():  # re-create the graphical items
            for item in graphics:
                self.removeItem(item)

        self._data_items = dict(data_items)
        self._data_graphics = {name: self._generate_plot_items(name, color) for name, color in data_items.items()}
        for graphics in self._data_graphics.values():
            for item in graphics:
                self.addItem(item)

        self.set_data(self._data)  # don't clear existing data

    def set_data(self, data: Mapping[str, Tuple[npt.NDArray[np.float64], npt.NDArray]]) -> None:
        """Updates data for plots defined in set_data_items."""
        self._data = dict(data)
        for data_name, (xs, ys) in data.items():
            graphics = self._data_graphics.get(data_name)
            if graphics is None:  # not pre-defined in set_data_items, ignore
                continue
            self._update_plot_data(data_name, graphics, xs, ys)

    @abstractmethod
    def _generate_plot_items(self, name: str, color: QColor) -> List[pg.GraphicsObject]:
        """Defines how to generate a pyqtgraph graphics item (eg, PlotCurveItem) from a data definition.
        May return multiple items, but the first one should be the main one. Must be nonempty.
        Only one should have a name, which is used for the legend.
        No data is passed in at this point, set_data will be called later.
        INTERNAL API - STABILITY NOT GUARANTEED"""
        raise NotImplementedError

    @abstractmethod
    def _update_plot_data(
        self, name: str, graphics: List[pg.GraphicsObject], xs: npt.NDArray[np.float64], ys: npt.NDArray
    ) -> None:
        """Called when the data is updated, but the data items (and graphical objects) remain the same.
        Not re-creating the graphical objects helps performance slightly.
        May apply transforms, such as for rendering efficiency.
        INTERNAL API - STABILITY NOT GUARANTEED"""
        raise NotImplementedError


class DataPlotCurveItem(DataPlotItem):
    """DataPlotItem that generates a PlotCurveItem"""

    def _generate_plot_items(self, name: str, color: QColor) -> List[pg.GraphicsObject]:
        curve = pg.PlotCurveItem(x=[], y=[], name=name)
        curve.setPen(color=color, width=1)
        return [curve]

    def _update_plot_data(
        self, name: str, graphics: List[pg.GraphicsObject], xs: npt.NDArray[np.float64], ys: npt.NDArray
    ) -> None:
        assert len(graphics) == 1
        curve = graphics[0]
        assert isinstance(curve, pg.PlotCurveItem)
        curve.setData(x=xs, y=ys)


class DeltaAxisItem(pg.AxisItem):  # type: ignore[misc]
    """An AxisItem that allows a different function for rendering delta time.
    Useful, eg, for timestamps where the axis is in wall clock format but deltas are in seconds.
    """

    @abstractmethod
    def deltaString(self, value: float, scale: float, spacing: float) -> str:
        return cast(str, self.tickStrings([value], scale, spacing))


class HoverSnapData(NamedTuple):
    hover_pos: QPointF  # in data coordinates
    snap_pos: Optional[QPointF]  # None if no nearby point


class HasDataValueAt(DataPlotItem):
    """Base class that provides a shared (and overrideable) function that returns multiple y-position and labels
    given some x position"""

    def _data_value_label_at(self, pos: float, precision_factor: float = 1.0) -> List[Tuple[float, str, QColor]]:
        outs = []
        for name, (xs, ys) in self._data.items():
            if name not in self._data_graphics or not self._data_graphics[name][0].isVisible():
                continue
            if not len(xs):
                continue

            index = bisect.bisect_left(xs, pos)
            if index < len(xs) and xs[index] == pos:  # found exact match
                outs.append(
                    (
                        ys[index],
                        LiveCursorPlot._value_axis_label(
                            ys[index],
                            self,
                            "left",
                            precision_factor=precision_factor,
                        ),
                        self._data_items[name],
                    )
                )
        return outs


class SnappableHoverPlot(DataPlotCurveItem):
    """Mixin for PlotItem that provides an optional snapped nearest data point on user hover.
    Shows a visual target on the snapped point."""

    sigHoverSnapChanged = Signal(HoverSnapData)  # emitted during mouseover when the mouse pos changes

    # TODO these belongs in RegionPlot / LiveCursorPlot, but it breaks with a signal / slots not ordered error
    sigHoverCursorChanged = Signal(object)  # Optional[float] = x-position
    sigCursorRangeChanged = Signal(object)  # Optional[Union[float, Tuple[float, float]]] as cursor / region
    sigPoiChanged = Signal(object)  # List[float] as current POIs
    sigDragCursorChanged = Signal(float)  # x-position
    sigDragCursorCleared = Signal()

    SNAP_DISTANCE_PX = 12
    MAX_PTS = 1024  # if more than this many points in the window, give up

    _Z_VALUE_SNAP_TARGET = 1000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hover_snap_point = HoverSnapData(QPointF(0, 0), None)  # stores the last hover state
        self._hover_target = pg.TargetItem(movable=False)
        self._hover_target.setZValue(self._Z_VALUE_SNAP_TARGET)
        self._hover_target.hide()
        self.addItem(self._hover_target, ignoreBounds=True)

    def _snap_pos(self, target_pos: QPointF, x_lo: float, x_hi: float) -> Optional[QPointF]:
        """Returns the closest point in the snappable data set to the target_pos, with x-value between x_lo and x_hi."""
        # closest point for each curve: (data, index, distance)
        data_index_dists: List[Tuple[Tuple[npt.NDArray[np.float64], npt.NDArray], int, float]] = []
        for name, (xs, ys) in self._data.items():
            data_graphics = self._data_graphics.get(name)
            if not data_graphics or not data_graphics[0].isVisible():
                continue
            if not len(xs):
                continue
            index_lo = bisect.bisect_left(xs, x_lo)
            index_hi = bisect.bisect_right(xs, x_hi)
            if index_hi - index_lo > self.MAX_PTS:
                continue

            # this code inspired by ScatterPlotItem._maskAt, which is used to find intersecting items fast
            px, py = data_graphics[0].pixelVectors()  # account for graph scaling
            if px is None or py is None or px.x() == 0 or py.y() == 0:  # invalid
                continue
            dxs = (xs[index_lo:index_hi] - target_pos.x()) / px.x()
            dys = (ys[index_lo:index_hi] - target_pos.y()) / py.y()
            dists = np.hypot(dxs, dys)
            if not len(dists):
                continue
            min_dist_index = int(np.argmin(dists))
            data_index_dists.append(((xs, ys), min_dist_index + index_lo, dists[min_dist_index]))

        if data_index_dists:
            (closest_xs, closest_ys), closest_index, _ = min(data_index_dists, key=lambda tup: tup[2])
            return QPointF(closest_xs[closest_index], closest_ys[closest_index])
        else:
            return None

    def hoverEvent(self, ev: HoverEvent) -> None:
        super().hoverEvent(ev)
        if ev.exit:  # use last data point, since position may not be available here
            snap_data = HoverSnapData(hover_pos=self.hover_snap_point.hover_pos, snap_pos=None)
            self._hover_target.hide()
            self.hover_snap_point = snap_data
            self.sigHoverSnapChanged.emit(snap_data)
            return

        pos = ev.pos()
        # based on pyqtgraph/examples/crosshair.py
        data_pos = cast(QPointF, self.mapToView(pos))
        data_lo = cast(
            QPointF,
            self.mapToView(QPointF(pos.x() - self.SNAP_DISTANCE_PX, pos.y())),
        )
        data_hi = cast(
            QPointF,
            self.mapToView(QPointF(pos.x() + self.SNAP_DISTANCE_PX, pos.y())),
        )
        snap_data = HoverSnapData(
            hover_pos=data_pos,
            snap_pos=self._snap_pos(data_pos, data_lo.x(), data_hi.x()),
        )

        if snap_data.snap_pos is not None:
            self._hover_target.show()
            self._hover_target.setPos(snap_data.snap_pos)
        else:
            self._hover_target.hide()

        self.hover_snap_point = snap_data
        self.sigHoverSnapChanged.emit(snap_data)


class LiveCursorPlot(SnappableHoverPlot, HasDataValueAt):
    """Mixin for PlotItem that displays a live snappable x-axis (vertical line) cursor that follows the user's mouse."""

    # TextItem anchor for the x position label
    LIVE_CURSOR_X_ANCHOR: Tuple[float, float] = (1, 1)
    # TextItem anchor for the y value label
    LIVE_CURSOR_Y_ANCHOR: Tuple[float, float] = (0, 1)

    _Z_VALUE_HOVER_TARGET = 100

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self._hover_cursor = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=mkPen(style=Qt.PenStyle.DotLine),
        )  # moves with hover not drag
        self._hover_cursor.hide()
        self.addItem(self._hover_cursor, ignoreBounds=True)

        self._hover_x_label = pg.TextItem(anchor=self.LIVE_CURSOR_X_ANCHOR)
        self._hover_x_label.hide()
        self.addItem(self._hover_x_label, ignoreBounds=True)

        # create one point that contains the data as a series, for efficiency
        self._hover_y_pts = ScatterItemCollection(self, z_value=self._Z_VALUE_HOVER_TARGET)
        self._hover_y_labels = TextItemCollection(
            self, anchor=self.LIVE_CURSOR_Y_ANCHOR, z_value=self._Z_VALUE_HOVER_TARGET
        )

        self.sigHoverSnapChanged.connect(self._update_live_cursor)

    def set_live_cursor(self, pos: Optional[float], pos_y: Optional[float] = None) -> None:
        """Sets the live cursor to some specified location, or deletes it (if None).
        If a y position is specified, draws the time label there, otherwise no time label.
        """
        if pos is not None:  # create or update live cursor
            self._hover_cursor.setPos(pos)
            self._hover_cursor.show()

            if pos_y is not None:
                self._hover_x_label.setPos(QPointF(pos, pos_y))  # y follows mouse, x is at cursor
                self._hover_x_label.setText(self._value_axis_label(pos, self, "bottom"))
                self._hover_x_label.show()
            else:
                self._hover_x_label.hide()

            x_y_text_colors = [
                (pos, y_pos, text, color) for y_pos, text, color in self._data_value_label_at(pos, precision_factor=0.1)
            ]
        else:  # delete live cursor
            self._hover_cursor.hide()
            self._hover_x_label.hide()

            x_y_text_colors = []

        self._hover_y_pts.update([(x_pos, y_pos, color) for x_pos, y_pos, text, color in x_y_text_colors])
        self._hover_y_labels.update(x_y_text_colors)

        self.sigHoverCursorChanged.emit(pos)

    def _update_live_cursor(self, snap_data: HoverSnapData) -> None:
        if snap_data.snap_pos is not None:
            curr_pos = snap_data.snap_pos
        else:
            curr_pos = snap_data.hover_pos
        self.set_live_cursor(curr_pos.x(), snap_data.hover_pos.y())

    def hoverEvent(self, ev: HoverEvent) -> None:
        super().hoverEvent(ev)
        if ev.exit:
            self.set_live_cursor(None)

    @staticmethod
    def _value_axis_label(
        value: float,
        plot: pg.PlotItem,
        axis_name: str,
        *,
        delta: bool = False,
        precision_factor: float = 1,
    ) -> str:
        """Returns a human-readable label for a value, as defined by the axis."""
        axis = cast(pg.AxisItem, plot.getAxis(axis_name))
        if axis_name in ("top", "bottom"):
            min_val = plot.viewRect().x()
            max_val = plot.viewRect().x() + plot.viewRect().width()
            size = plot.size().width()
        elif axis_name in ("left", "right"):
            min_val = plot.viewRect().y()
            max_val = plot.viewRect().y() + plot.viewRect().height()
            size = plot.size().height()
        else:
            raise ValueError

        if size <= 0:  # avoid div0
            size = 1
        tick_spacings = axis.tickSpacing(min_val, max_val, size)
        if not tick_spacings:
            return str(value)  # fallback, can happen when the user zooms way the heck out
        tick_spacing = tick_spacings[-1][0]  # take finest tick spacing for resolution

        if axis.labelUnits:  # do SI prefixing if it has units
            if delta and isinstance(axis, DeltaAxisItem):
                value_str = axis.deltaString(
                    value,
                    axis.scale * axis.autoSIPrefixScale,
                    tick_spacing * precision_factor,
                )[0]
            else:
                value_str = axis.tickStrings(
                    [value],
                    axis.scale * axis.autoSIPrefixScale,
                    tick_spacing * precision_factor,
                )[0]
            return f"{value_str} {axis.labelUnitPrefix}{axis.labelUnits}"
        else:
            if delta and isinstance(axis, DeltaAxisItem):
                return axis.deltaString(value, axis.scale, tick_spacing * precision_factor)[0]
            else:
                return cast(
                    str,
                    axis.tickStrings([value], axis.scale, tick_spacing * precision_factor)[0],
                )


class RegionPlot(SnappableHoverPlot):
    """Mixin for PlotItem that allows the user to create a region on the x-axis.
    The region only displays the span length, but can be infrastructure for other functions.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.cursor: Optional[pg.InfiniteLine] = None
        self._cursor_left_label: Optional[pg.TextItem] = None
        self._cursor_right_label: Optional[pg.TextItem] = None
        self.cursor_range: Optional[pg.LinearRegionItem] = None
        self._last_cursor_range = (0.0, 0.0)  # to detect which end is dragged
        self._cursor_range_label: Optional[pg.TextItem] = None

        self.show_cursor_range_labels = True
        self.sigRangeChanged.connect(self._update_cursor_labels)

    def set_region(self, region: Optional[Union[float, Tuple[float, float]]]) -> None:
        """Creates a cursor / region at the bounds, or moves the existing cursor / region if it exists.
        If none, deletes the existing region / cursor.
        External API for interactivity and testing."""
        if isinstance(region, tuple):
            if self.cursor is not None:
                self.removeItem(self.cursor)
                self.cursor = None
            if self.cursor_range is None:
                self.cursor_range = pg.LinearRegionItem(movable=True)
                self.cursor_range.sigRegionChanged.connect(self._on_region_drag)
                self.addItem(self.cursor_range, ignoreBounds=True)
            self._last_cursor_range = region
            with QSignalBlocker(self.cursor_range):
                self.cursor_range.setRegion(self._last_cursor_range)

            self._update_cursor_labels()
            self.sigCursorRangeChanged.emit(self.cursor_range.getRegion())
        elif isinstance(region, float):
            if self.cursor_range is not None:
                self.removeItem(self.cursor_range)
                self.cursor_range = None
            if self.cursor is None:
                self.cursor = pg.InfiniteLine(movable=True)
                self.cursor.sigDragged.connect(self._on_cursor_drag)
                self.addItem(self.cursor, ignoreBounds=True)
            with QSignalBlocker(self.cursor):
                self.cursor.setPos(region)

            self._update_cursor_labels()
            self.sigCursorRangeChanged.emit(self.cursor.pos().x())
        elif region is None:
            if self.cursor is not None:
                self.removeItem(self.cursor)
                self.cursor = None
            if self.cursor_range is not None:
                self.removeItem(self.cursor_range)
                self.cursor_range = None
            self._update_cursor_labels()
            self.sigCursorRangeChanged.emit(None)
        else:
            raise ValueError(f"unexpected region {region}")

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        if event.modifiers() != Qt.KeyboardModifier.NoModifier:
            return

        if self.hover_snap_point.snap_pos is not None:  # prefer to insert at snap location
            create_pos = self.hover_snap_point.snap_pos
        else:
            create_pos = self.hover_snap_point.hover_pos

        if self.cursor is None and self.cursor_range is None:  # nothing, create single cursor as first step
            self.set_region(create_pos.x())
        elif self.cursor is not None and self.cursor_range is None:  # cursor exists, upgrade to region
            self.set_region((self.cursor.x(), create_pos.x()))
        elif self.cursor_range is not None:  # move nearest region bound to cursor
            cursor_region = self.cursor_range.getRegion()
            dist_0 = abs(create_pos.x() - cursor_region[0])
            dist_1 = abs(create_pos.x() - cursor_region[1])
            if dist_0 <= dist_1:
                self.set_region((create_pos.x(), cursor_region[1]))
            else:
                self.set_region((cursor_region[0], create_pos.x()))

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        super().keyPressEvent(ev)
        if ev.key() == Qt.Key.Key_Delete:
            if self.cursor is not None and self.cursor.mouseHovering:  # remove current item if hovered
                self.set_region(None)
            elif self.cursor_range is not None and (
                self.cursor_range.lines[0].mouseHovering or self.cursor_range.lines[1].mouseHovering  # remove bound
            ):
                if self.cursor_range.lines[0].mouseHovering:  # if hovering over a line, 'delete' the line
                    self.set_region(self.cursor_range.lines[1].pos().x())
                else:
                    self.set_region(self.cursor_range.lines[0].pos().x())
            elif self.cursor_range is not None and self.cursor_range.mouseHovering:  # remove region
                self.set_region(None)

    @Slot()
    def _update_cursor_labels(self) -> None:
        if self.cursor_range is not None:
            if self._cursor_left_label is None and self.show_cursor_range_labels:
                self._cursor_left_label = pg.TextItem("", anchor=(1, 1))
                self.addItem(self._cursor_left_label, ignoreBounds=True)
            elif self._cursor_left_label is not None and not self.show_cursor_range_labels:
                self.removeItem(self._cursor_left_label)
                self._cursor_left_label = None
            if self._cursor_right_label is None and self.show_cursor_range_labels:
                self._cursor_right_label = pg.TextItem("", anchor=(0, 1))
                self.addItem(self._cursor_right_label, ignoreBounds=True)
            elif self._cursor_right_label is not None and not self.show_cursor_range_labels:
                self.removeItem(self._cursor_right_label)
                self._cursor_right_label = None
            if self._cursor_range_label is None and self.show_cursor_range_labels:
                self._cursor_range_label = pg.TextItem("", anchor=(0.5, 1))
                self.addItem(self._cursor_range_label, ignoreBounds=True)
            elif self._cursor_range_label is not None and not self.show_cursor_range_labels:
                self.removeItem(self._cursor_range_label)
                self._cursor_range_label = None

            if self._cursor_left_label is not None:
                self._cursor_left_label.setText(
                    LiveCursorPlot._value_axis_label(self.cursor_range.getRegion()[0], self, "bottom")
                )
                self._cursor_left_label.setPos(QPointF(self.cursor_range.getRegion()[0], self.viewRect().y()))
            if self._cursor_right_label is not None:
                self._cursor_right_label.setText(
                    LiveCursorPlot._value_axis_label(self.cursor_range.getRegion()[1], self, "bottom")
                )
                self._cursor_right_label.setPos(QPointF(self.cursor_range.getRegion()[1], self.viewRect().y()))
            if self._cursor_range_label is not None:
                self._cursor_range_label.setText(
                    LiveCursorPlot._value_axis_label(
                        self.cursor_range.getRegion()[1] - self.cursor_range.getRegion()[0],
                        self,
                        "bottom",
                        delta=True,
                    )
                )
                range_left_bound = max(self.cursor_range.getRegion()[0], self.viewRect().x())
                range_right_bound = min(
                    self.cursor_range.getRegion()[1],
                    self.viewRect().x() + self.viewRect().width(),
                )
                self._cursor_range_label.setPos(
                    QPointF(
                        (range_left_bound + range_right_bound) / 2,
                        self.viewRect().y(),
                    )
                )
        elif self.cursor is not None:
            if self._cursor_left_label is None and self.show_cursor_range_labels:
                self._cursor_left_label = pg.TextItem("", anchor=(1, 1))
                self.addItem(self._cursor_left_label, ignoreBounds=True)
            elif self._cursor_left_label is not None and not self.show_cursor_range_labels:
                self.removeItem(self._cursor_left_label)
                self._cursor_left_label = None
            if self._cursor_right_label is not None:
                self.removeItem(self._cursor_right_label)
                self._cursor_right_label = None
            if self._cursor_range_label is not None:
                self.removeItem(self._cursor_range_label)
                self._cursor_range_label = None

            if self._cursor_left_label:
                self._cursor_left_label.setText(LiveCursorPlot._value_axis_label(self.cursor.pos().x(), self, "bottom"))
                self._cursor_left_label.setPos(QPointF(self.cursor.pos().x(), self.viewRect().y()))
        else:
            if self._cursor_left_label is not None:
                self.removeItem(self._cursor_left_label)
                self._cursor_left_label = None
            if self._cursor_right_label is not None:
                self.removeItem(self._cursor_right_label)
                self._cursor_right_label = None
            if self._cursor_range_label is not None:
                self.removeItem(self._cursor_range_label)
                self._cursor_range_label = None

    def _on_cursor_drag(self, x: Any) -> None:
        if self.cursor is None:
            return
        if self.hover_snap_point.snap_pos is not None:
            self.cursor.setPos(self.hover_snap_point.snap_pos)
        self._update_cursor_labels()
        self.sigCursorRangeChanged.emit(self.cursor.pos().x())

    def _on_region_drag(self, x: Any) -> None:
        if self.cursor_range is None:
            return
        self.sigCursorRangeChanged.emit(self.cursor_range.getRegion())
        with QSignalBlocker(self.cursor_range):
            if self.hover_snap_point.snap_pos:
                new_region = self.cursor_range.getRegion()
                # TODO automatically handle range inversion
                if new_region[1] != self._last_cursor_range[1] and new_region[0] == self._last_cursor_range[0]:
                    self.cursor_range.setRegion((new_region[0], self.hover_snap_point.snap_pos.x()))
                elif new_region[0] != self._last_cursor_range[0] and new_region[1] == self._last_cursor_range[1]:
                    self.cursor_range.setRegion((self.hover_snap_point.snap_pos.x(), new_region[1]))
        self._last_cursor_range = self.cursor_range.getRegion()
        self._update_cursor_labels()
        self.sigCursorRangeChanged.emit(self.cursor_range.getRegion())


class PointsOfInterestPlot(SnappableHoverPlot, HasDataValueAt):
    """Mixin for PlotItem that allows the user to create points of interest on the x-axis,
    each of which shows y-axis values."""

    POI_ANCHOR: Tuple[float, float] = (0, 1)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.pois: List[pg.InfiniteLine] = []  # lines
        self._poi_items: Dict[pg.InfiniteLine, Tuple[ScatterItemCollection, TextItemCollection]] = {}

        self.sigRangeChanged.connect(self._update_all_poi_labels)

    def set_pois(self, pois: List[float]) -> None:
        for _ in range(len(self.pois), len(pois)):  # POIs to be added
            self._add_poi(0)
        for _ in range(len(pois), len(self.pois)):  # POIs to be removed
            self._remove_poi(self.pois[-1])
        assert len(self.pois) == len(pois)
        for poi, pos in zip(self.pois, pois):
            poi.setPos(pos)
            self._update_poi(poi)
        self.sigPoiChanged.emit([poi.x() for poi in self.pois])

    def _on_poi_drag(self, cursor: pg.InfiniteLine) -> None:
        if self.hover_snap_point.snap_pos is not None:
            cursor.setPos(self.hover_snap_point.snap_pos)
        self._update_poi(cursor)
        self.sigPoiChanged.emit([poi.x() for poi in self.pois])

    def _update_poi(self, cursor: pg.InfiniteLine) -> None:
        scatter, texts = self._poi_items[cursor]
        x_y_text_color = [
            (cursor.x(), y_pos, text, color)
            for y_pos, text, color in self._data_value_label_at(cursor.x(), precision_factor=0.1)
        ]
        scatter.update([(x_pos, y_pos, color) for x_pos, y_pos, text, color in x_y_text_color])
        texts.update(x_y_text_color)

    @Slot()
    def _update_all_poi_labels(self) -> None:
        """Regenerate text for all POI labels, eg to account for scale changes"""
        for line, _ in self._poi_items.items():
            self._update_poi(line)

    def set_data(self, *args: Any, **kwargs: Any) -> None:
        super().set_data(*args, **kwargs)
        self._update_all_poi_labels()  # update if plot changed

    def _add_poi(self, pos: float) -> None:
        """Adds a new POI at the location"""
        cursor = pg.InfiniteLine(movable=True)
        cursor.setPos((pos, 0))
        cursor.sigDragged.connect(self._on_poi_drag)
        self.addItem(cursor, ignoreBounds=True)
        self.pois.append(cursor)
        self._poi_items[cursor] = (ScatterItemCollection(self), TextItemCollection(self, anchor=self.POI_ANCHOR))
        self._update_poi(cursor)

    def _remove_poi(self, cursor: pg.InfiniteLine) -> None:
        scatter, texts = self._poi_items[cursor]
        scatter.remove()
        texts.remove()
        del self._poi_items[cursor]
        self.pois.remove(cursor)
        self.removeItem(cursor)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        if event.modifiers() != Qt.KeyboardModifier.ShiftModifier:
            return

        if self.hover_snap_point.snap_pos is not None:  # prefer to insert at snap location
            create_pos = self.hover_snap_point.snap_pos
        else:
            create_pos = self.hover_snap_point.hover_pos

        if create_pos.x() not in [poi.pos().x() for poi in self.pois]:  # don't duplicate
            self._add_poi(create_pos.x())
            self.sigPoiChanged.emit([poi.x() for poi in self.pois])

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        super().keyPressEvent(ev)
        if ev.key() == Qt.Key.Key_Delete:
            for poi in reversed(self.pois):
                if poi.mouseHovering:
                    self._remove_poi(poi)
            self.sigPoiChanged.emit([poi.x() for poi in self.pois])


class NudgeablePlot(HasDataValueAt):
    def _next_x_pos(self, curr_pos: float, dir: int) -> Optional[float]:
        candidate: Optional[float] = None
        for name, (xs, ys) in self._data.items():
            data_graphics = self._data_graphics.get(name)
            if not data_graphics or not data_graphics[0].isVisible():
                continue
            if not len(xs):
                continue
            if dir < 0:  # find previous
                index = bisect.bisect_left(xs, curr_pos) - 1
            else:  # find next
                index = bisect.bisect_right(xs, curr_pos)
            if index < 0 or index >= len(xs):  # out of bounds
                continue
            next_pos = xs[index]
            if candidate is None or abs(next_pos - curr_pos) < abs(candidate - curr_pos):
                candidate = next_pos
        return candidate

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        super().keyPressEvent(ev)
        if ev.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            dir = -1 if ev.key() == Qt.Key.Key_Left else 1
            if isinstance(self, LiveCursorPlot):
                if self._hover_cursor.isVisible():
                    next_pos = self._next_x_pos(self._hover_cursor.pos().x(), dir)
                    if next_pos is not None:
                        self.set_live_cursor(next_pos)
            if isinstance(self, RegionPlot):
                if self.cursor_range is not None and self.cursor_range.mouseHovering:
                    curr_start_pos, curr_end_pos = self.cursor_range.getRegion()
                    next_end_pos = self._next_x_pos(curr_end_pos, dir)
                    if next_end_pos is not None:
                        self.set_region((curr_start_pos + next_end_pos - curr_end_pos, next_end_pos))


class DraggableCursorPlot(SnappableHoverPlot, HasDataValueAt):
    """Mixin for PlotItem that allows a programmatically created draggable time-cursor,
    which generates a signal when it is moved.
    Only one cursor may be active at a time."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.drag_cursor: Optional[pg.InfiniteLine] = None

    def set_drag_cursor(self, pos: Optional[float]) -> None:
        """If pos is none, delete the drag cursor (if any)
        If pos is not none, create (or move) the drag cursor to the location."""
        if pos is None:
            if self.drag_cursor is not None:
                self.removeItem(self.drag_cursor)
                self.drag_cursor = None
                self.sigDragCursorCleared.emit()
        else:
            if self.drag_cursor is None:
                self.drag_cursor = pg.InfiniteLine(movable=True)
                self.drag_cursor.sigDragged.connect(self._on_drag_cursor_drag)
                self.addItem(self.drag_cursor)
            self.drag_cursor.setPos(pos)
            self.sigDragCursorChanged.emit(pos)

    def _on_drag_cursor_drag(self, cursor: pg.InfiniteLine) -> None:
        if self.hover_snap_point.snap_pos is not None:
            cursor.setPos(self.hover_snap_point.snap_pos)
        self.sigDragCursorChanged.emit(cursor.pos().x())

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        super().keyPressEvent(ev)
        if ev.key() == Qt.Key.Key_Escape:
            self.set_drag_cursor(None)
        elif ev.key() == Qt.Key.Key_Delete:
            self.set_drag_cursor(None)
