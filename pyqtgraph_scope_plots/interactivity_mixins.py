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
import math
from abc import abstractmethod
from typing import List, Tuple, Dict, Optional, Any, cast, NamedTuple, Union

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QSignalBlocker, Signal, Slot
from PySide6.QtGui import Qt, QColor, QKeyEvent
from PySide6.QtWidgets import QGraphicsSceneMouseEvent
from pyqtgraph import mkPen
from pyqtgraph.GraphicsScene.mouseEvents import HoverEvent


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


class HasDataValueAt(pg.PlotItem):  # type: ignore[misc]
    """Base class that provides a shared (and overrideable) function that returns multiple y-position and labels
    given some x position"""

    def _data_value_label_at(self, pos: float, precision_factor: float = 1.0) -> List[Tuple[float, str, QColor]]:
        outs = []
        for data_item in self.listDataItems():  # type: pg.PlotDataItem
            if not isinstance(data_item, pg.PlotCurveItem):  # ignore scatter points
                continue
            if not data_item.isVisible():
                continue
            xpts, ypts = data_item.getData()
            if xpts is None or not len(xpts):
                continue
            index = bisect.bisect_left(xpts, pos)
            if index < len(xpts) and xpts[index] == pos:  # found exact match
                outs.append(
                    (
                        ypts[index],
                        LiveCursorPlot._value_axis_label(
                            ypts[index],
                            self,
                            "left",
                            precision_factor=precision_factor,
                        ),
                        mkPen(data_item.opts["pen"]).color(),  # opts['pen'] has multiple formats
                    )
                )
        return outs


class SnappableHoverPlot(pg.PlotItem):  # type: ignore[misc]
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
    MAX_PTS = 128  # if more than this many points in the window, give up

    _Z_VALUE_SNAP_TARGET = 1000

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.hover_snap_point = HoverSnapData(QPointF(0, 0), None)  # stores the last hover state
        self._hover_target: Optional[pg.TargetItem] = None

    def _snap_pos(self, target_pos: QPointF, x_lo: float, x_hi: float) -> Optional[QPointF]:
        """Returns the closest point in the snappable data set to the target_pos, with x-value between x_lo and x_hi.
        Pulls from self.listDataItems() by default, override this to provide different snapping points.
        """
        # closest point for each curve: (curve, index, distance)
        curve_index_dist: List[Tuple[pg.PlotDataItem, int, float]] = []
        visible_data_items = [data_item for data_item in self.listDataItems() if data_item.isVisible()]
        for data_item in visible_data_items:  # type: pg.PlotDataItem
            xpts, ypts = data_item.getData()
            if xpts is None or not len(xpts):
                continue
            index_lo = bisect.bisect_left(xpts, x_lo)
            index_hi = bisect.bisect_right(xpts, x_hi)
            if index_hi - index_lo > self.MAX_PTS:
                continue

            # compare in screen coordination since X/Y scaling may not be uniform
            index_dist = self._closest_index(
                [
                    self.mapFromView(QPointF(xpt, ypt))
                    for xpt, ypt in zip(xpts[index_lo:index_hi], ypts[index_lo:index_hi])
                ],
                self.mapFromView(target_pos),
            )
            if index_dist is None:
                continue
            curve_index_dist.append((data_item, index_dist[0] + index_lo, index_dist[1]))

        if curve_index_dist:
            closest_item = min(curve_index_dist, key=lambda tup: tup[2])
            closest_curve, closest_index, _ = closest_item
            closest_xs, closest_ys = closest_curve.getData()
            return QPointF(closest_xs[closest_index], closest_ys[closest_index])
        else:
            return None

    def hoverEvent(self, ev: HoverEvent) -> None:
        super().hoverEvent(ev)

        if ev.exit:  # use last data point, since position may not be available here
            snap_data = HoverSnapData(hover_pos=self.hover_snap_point.hover_pos, snap_pos=None)
            if self._hover_target is not None:
                self.removeItem(self._hover_target)
                self._hover_target = None
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
            if self._hover_target is None:
                self._hover_target = pg.TargetItem(movable=False)
                self._hover_target.setZValue(self._Z_VALUE_SNAP_TARGET)
                self.addItem(self._hover_target, ignoreBounds=True)
            self._hover_target.setPos(snap_data.snap_pos)
        else:
            if self._hover_target is not None:
                self.removeItem(self._hover_target)
                self._hover_target = None

        self.hover_snap_point = snap_data
        self.sigHoverSnapChanged.emit(snap_data)

    @staticmethod
    def _closest_index(pts: List[QPointF], pos: QPointF) -> Optional[Tuple[int, float]]:
        """Returns the (index, dist) of the closest point (by xy distance) to (xpos, ypos) in the series xpts, ypts.
        Returns None if no point is found."""
        # TODO use collective operations for performance
        dists = [math.sqrt((pos.x() - pt.x()) ** 2 + (pos.y() - pt.y()) ** 2) for pt in pts]
        if not dists:
            return None
        min_dist_index = np.argmin(dists)
        min_dist = dists[min_dist_index]
        return int(min_dist_index), min_dist


class LiveCursorPlot(SnappableHoverPlot, HasDataValueAt):
    """Mixin for PlotItem that displays a live snappable x-axis (vertical line) cursor that follows the user's mouse."""

    # TextItem anchor for the x position label
    LIVE_CURSOR_X_ANCHOR: Tuple[float, float] = (1, 1)
    # TextItem anchor for the y value label
    LIVE_CURSOR_Y_ANCHOR: Tuple[float, float] = (0, 1)

    _Z_VALUE_HOVER_TARGET = 100

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.hover_cursor: Optional[pg.InfiniteLine] = None
        self._hover_x_label: Optional[pg.TextItem] = None
        self._hover_y_pts: List[pg.ScatterPlotItem] = []
        self._hover_y_labels: List[pg.TextItem] = []

        self.sigHoverSnapChanged.connect(self._update_live_cursor)

    def set_live_cursor(self, pos: Optional[float], pos_y: Optional[float] = None) -> None:
        """Sets the live cursor to some specified location, or deletes it (if None).
        If a y position is specified, draws the time label there, otherwise no time label.
        """
        for pts in self._hover_y_pts:  # clear old widgets as needed, then re-create
            self.removeItem(pts)
        self._hover_y_pts = []
        for label in self._hover_y_labels:
            self.removeItem(label)
        self._hover_y_labels = []

        if pos is not None:  # create or update live cursor
            if self.hover_cursor is None:  # create new widgets as needed
                self.hover_cursor = pg.InfiniteLine(
                    angle=90,
                    movable=False,
                    pen=mkPen(style=Qt.PenStyle.DotLine),
                )  # moves with hover not drag
                self.addItem(self.hover_cursor, ignoreBounds=True)
            self.hover_cursor.setPos(pos)

            if pos_y is not None:
                if self._hover_x_label is None:
                    self._hover_x_label = pg.TextItem(anchor=self.LIVE_CURSOR_X_ANCHOR)
                    self.addItem(self._hover_x_label, ignoreBounds=True)
                self._hover_x_label.setPos(QPointF(pos, pos_y))  # y follows mouse, x is at cursor
                self._hover_x_label.setText(self._value_axis_label(pos, self, "bottom"))
            else:
                if self._hover_x_label is not None:
                    self.removeItem(self._hover_x_label)
                    self._hover_x_label = None

            for y_pos, text, color in self._data_value_label_at(pos, precision_factor=0.1):
                hover_pt = pg.ScatterPlotItem(x=[pos], y=[y_pos], symbol="o", brush=color)
                hover_pt.setZValue(self._Z_VALUE_HOVER_TARGET)
                self.addItem(hover_pt, ignoreBounds=True)
                self._hover_y_pts.append(hover_pt)
                hover_label = pg.TextItem(text, anchor=self.LIVE_CURSOR_Y_ANCHOR, color=color)
                hover_label.setZValue(self._Z_VALUE_HOVER_TARGET)
                hover_label.setPos(QPointF(pos, y_pos))
                self.addItem(hover_label, ignoreBounds=True)
                self._hover_y_labels.append(hover_label)
        else:  # delete live cursor
            if self.hover_cursor is not None:
                self.removeItem(self.hover_cursor)
                self.hover_cursor = None
            if self._hover_x_label is not None:
                self.removeItem(self._hover_x_label)
                self._hover_x_label = None
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
        self._poi_items: Dict[pg.InfiniteLine, List[Union[pg.GraphicsObject]]] = {}

        self.sigRangeChanged.connect(self._update_all_poi_labels)

    def set_pois(self, pois: List[float]) -> None:
        for poi, items in self._poi_items.items():
            self.removeItem(poi)
            for item in items:
                self.removeItem(item)
        self.pois = []
        self._poi_items = {}

        for poi in pois:
            self._add_poi(poi)

    def _on_poi_drag(self, cursor: pg.InfiniteLine) -> None:
        if self.hover_snap_point.snap_pos is not None:
            cursor.setPos(self.hover_snap_point.snap_pos)
        for item in self._poi_items[cursor]:
            self.removeItem(item)
        self._poi_items[cursor] = []
        self._generate_poi_items(cursor)
        self.sigPoiChanged.emit([poi.x() for poi in self.pois])

    def _generate_poi_items(self, cursor: pg.InfiniteLine) -> None:
        for y_pos, text, color in self._data_value_label_at(cursor.x(), precision_factor=0.1):
            poi_pt = pg.ScatterPlotItem(x=[cursor.x()], y=[y_pos], symbol="o", brush=color)
            self.addItem(poi_pt, ignoreBounds=True)
            self._poi_items[cursor].append(poi_pt)
            y_label = pg.TextItem(anchor=self.POI_ANCHOR)
            y_label.setPos(QPointF(cursor.x(), y_pos))
            y_label.setText(text)
            y_label.setColor(color)
            self.addItem(y_label, ignoreBounds=True)
            self._poi_items[cursor].append(y_label)

    @Slot()
    def _update_all_poi_labels(self) -> None:
        """Regenerate text for all POI labels, eg to account for scale changes"""
        for line, items in self._poi_items.items():
            for item in items:
                self.removeItem(item)
            self._poi_items[line] = []
            self._generate_poi_items(line)

    def addItem(self, item: Any, *args: Any, **kargs: Any) -> None:
        super().addItem(item, *args, **kargs)
        if isinstance(item, pg.PlotCurveItem):  # update labels if plot changed
            self._update_all_poi_labels()

    def removeItem(self, item: Any) -> None:
        super().removeItem(item)
        if isinstance(item, pg.PlotCurveItem):  # update labels if plot changed
            self._update_all_poi_labels()

    def _add_poi(self, pos: float) -> None:
        if pos in [cursor.pos().x() for cursor in self.pois]:
            return  # don't double-create

        cursor = pg.InfiniteLine(movable=True)
        cursor.setPos((pos, 0))
        cursor.sigDragged.connect(self._on_poi_drag)
        self.addItem(cursor, ignoreBounds=True)
        self.pois.append(cursor)
        self._poi_items[cursor] = []
        self._generate_poi_items(cursor)
        self.sigPoiChanged.emit([poi.x() for poi in self.pois])

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        if event.modifiers() != Qt.KeyboardModifier.ShiftModifier:
            return

        if self.hover_snap_point.snap_pos is not None:  # prefer to insert at snap location
            create_pos = self.hover_snap_point.snap_pos
        else:
            create_pos = self.hover_snap_point.hover_pos
        self._add_poi(create_pos.x())

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        super().keyPressEvent(ev)
        if ev.key() == Qt.Key.Key_Delete:
            deleted = False
            for poi in reversed(self.pois):
                if poi.mouseHovering:
                    if poi in self._poi_items:
                        for item in self._poi_items[poi]:
                            self.removeItem(item)
                        del self._poi_items[poi]
                    self.pois.remove(poi)
                    self.removeItem(poi)
                    deleted = True
            if deleted:
                self.sigPoiChanged.emit([poi.x() for poi in self.pois])


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
