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

from typing import cast

import pyqtgraph as pg
from PySide6.QtCore import QPointF, QPoint, QEvent
from PySide6.QtGui import QColor, Qt, QMouseEvent
from pyqtgraph import PlotCurveItem
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.util.util import not_none
from pyqtgraph_scope_plots.interactivity_mixins import PointsOfInterestPlot, LiveCursorPlot, RegionPlot


def data_to_screen(plot_item: pg.PlotItem, x: float, y: float) -> QPoint:
    return cast(QPointF, plot_item.mapFromView(QPointF(x, y))).toPoint()


def init_plot(qtbot: QtBot, plot: pg.PlotWidget) -> None:
    plot.addItem(PlotCurveItem(x=[0, 0.1, 1, 2], y=[0.01, 1, 1, 0], pen={"color": QColor("yellow")}))
    plot.addItem(PlotCurveItem(x=[0, 1, 2], y=[0.5, 0.25, 0.5], pen={"color": QColor("orange")}))
    plot.addItem(PlotCurveItem(x=[0, 1, 2], y=[0.7, 0.6, 0.5], pen={"color": QColor("blue")}))
    qtbot.wait(100)  # wait for plot to initialize and range to stabilize
    qtbot.mouseMove(plot.viewport(), QPoint(0, 0))  # provide initial position for hover
    qtbot.wait(100)


def test_snap_api(qtbot: QtBot) -> None:
    plot_item = LiveCursorPlot()
    plot = pg.PlotWidget(plotItem=plot_item)
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    init_plot(qtbot, plot)

    assert not_none(plot_item._snap_pos(QPointF(0.1, 1), -1, 3)) == QPointF(0.1, 1)  # exact snap
    assert not_none(plot_item._snap_pos(QPointF(0.2, 1), -1, 3)) == QPointF(0.1, 1)  # nearby snap
    assert not_none(plot_item._snap_pos(QPointF(0.2, 1.1), -1, 3)) == QPointF(0.1, 1)
    assert not_none(plot_item._snap_pos(QPointF(0.1, 1.1), -1, 3)) == QPointF(0.1, 1)
    assert not_none(plot_item._snap_pos(QPointF(0, 1.1), -1, 3)) == QPointF(0.1, 1)  # disambiguate with closer point

    assert not_none(plot_item._snap_pos(QPointF(1, 0), 0.5, 1.5)) == QPointF(1, 0.25)  # disambiguate with other curves
    assert not_none(plot_item._snap_pos(QPointF(1, 0.5), 0.5, 1.5)) == QPointF(1, 0.6)
    assert not_none(plot_item._snap_pos(QPointF(1, 0.9), 0.5, 1.5)) == QPointF(1, 1)


def test_data_values_api(qtbot: QtBot) -> None:
    plot_item = PointsOfInterestPlot()
    plot = pg.PlotWidget(plotItem=plot_item)
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    init_plot(qtbot, plot)

    assert plot_item._data_value_label_at(0) == [
        (0.01, "0.01", QColor("yellow")),
        (0.5, "0.50", QColor("orange")),
        (0.7, "0.70", QColor("blue")),
    ]

    assert plot_item._data_value_label_at(1.0) == [
        (1, "1.00", QColor("yellow")),
        (0.25, "0.25", QColor("orange")),
        (0.6, "0.60", QColor("blue")),
    ]

    assert plot_item._data_value_label_at(0.1) == [(1, "1.00", QColor("yellow"))]


def test_snap_gui(qtbot: QtBot) -> None:
    """Subset of the snapping API tests that go through the GUI"""
    plot_item = LiveCursorPlot()
    plot = pg.PlotWidget(plotItem=plot_item)
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    init_plot(qtbot, plot)

    # note, qtbot.mouseMove doesn't work in a headless environment, so directly fire mouse-move events
    # try to snap exactly on (0.1, 1)
    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 0.1, 1),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: not_none(plot_item._hover_target).pos() == QPointF(0.1, 1))
    assert not_none(plot_item.hover_snap_point.snap_pos) == QPointF(0.1, 1)
    assert [label.color for label in plot_item._hover_y_labels] == [QColor("yellow")]
    assert [label.toPlainText() for label in plot_item._hover_y_labels] == ["1.000"]  # single label only

    # disambiguate on target with shared x axis
    qtbot.wait(10)  # pyqtgraph rate-limits, so add a wait
    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 1, 0),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: not_none(plot_item._hover_target).pos() == QPointF(1, 0.25))
    assert not_none(plot_item.hover_snap_point.snap_pos) == QPointF(1, 0.25)
    assert plot_item.hover_cursor.pos().x() == 1
    assert [label.toPlainText() for label in plot_item._hover_y_labels] == ["1.000", "0.250", "0.600"]
    assert [label.color for label in plot_item._hover_y_labels] == [QColor("yellow"), QColor("orange"), QColor("blue")]

    # off screen, cursor should disappear
    qtbot.wait(10)
    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 10, 10),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: plot_item.hover_cursor is None)


def test_range_gui(qtbot: QtBot) -> None:
    plot_item = RegionPlot()
    plot = pg.PlotWidget(plotItem=plot_item)
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    init_plot(qtbot, plot)

    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 0.1, 1),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: not_none(plot_item.hover_snap_point.snap_pos) == QPointF(0.1, 1))
    qtbot.mouseDClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 0.1, 1))
    qtbot.waitUntil(lambda: plot_item.cursor is not None)
    assert plot_item.cursor.pos().x() == 0.1

    qtbot.wait(10)  # pyqtgraph rate-limits, so add a wait
    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 2.0, 0),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: not_none(plot_item.hover_snap_point.snap_pos) == QPointF(2, 0))
    qtbot.mouseDClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 2, 0))
    qtbot.waitUntil(lambda: plot_item.cursor_range is not None and plot_item.cursor is None)
    assert plot_item.cursor_range.getRegion() == (0.1, 2.0)
    assert plot_item._cursor_range_label is not None and plot_item._cursor_range_label.toPlainText() == "1.90"

    # test expansion
    qtbot.wait(10)
    plot.mouseMoveEvent(
        QMouseEvent(
            QEvent.Type.HoverMove,
            data_to_screen(plot_item, 0, 0.001),
            QPointF(0, 0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    qtbot.waitUntil(lambda: not_none(plot_item.hover_snap_point.snap_pos) == QPointF(0, 0.01))
    qtbot.mouseDClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 0, 0.01))
    qtbot.waitUntil(lambda: plot_item.cursor_range.getRegion() == (0, 2.0))

    # test deletion of bound
    qtbot.mouseClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 0, 1))
    qtbot.waitUntil(lambda: plot_item.cursor_range.lines[0].mouseHovering)
    qtbot.keyClick(plot.viewport(), Qt.Key.Key_Delete)
    qtbot.waitUntil(lambda: plot_item.cursor_range is None and plot_item.cursor is not None)
    assert plot_item.cursor.pos().x() == 2.0

    # test deletion of cursor
    qtbot.mouseClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 2.0, 0))
    qtbot.waitUntil(lambda: plot_item.cursor.mouseHovering)
    qtbot.keyClick(plot.viewport(), Qt.Key.Key_Delete)
    qtbot.waitUntil(lambda: plot_item.cursor is None)


def test_poi_gui(qtbot: QtBot) -> None:
    plot_item = PointsOfInterestPlot()
    plot = pg.PlotWidget(plotItem=plot_item)
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    init_plot(qtbot, plot)

    qtbot.mouseDClick(
        plot.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        pos=data_to_screen(plot_item, 0, 0) + QPoint(10, 10),
    )
    qtbot.waitUntil(lambda: len(plot_item.pois) == 1)
    assert plot_item.pois[0].pos().x() == 0
    assert len(plot_item._poi_items[plot_item.pois[0]]) == 3 * 2
    assert plot_item._poi_items[plot_item.pois[0]][1].toPlainText() == "0.010"
    assert plot_item._poi_items[plot_item.pois[0]][1].color == QColor("yellow")
    assert plot_item._poi_items[plot_item.pois[0]][3].toPlainText() == "0.500"
    assert plot_item._poi_items[plot_item.pois[0]][3].color == QColor("orange")
    assert plot_item._poi_items[plot_item.pois[0]][5].toPlainText() == "0.700"
    assert plot_item._poi_items[plot_item.pois[0]][5].color == QColor("blue")

    # must be near-exact
    qtbot.mouseClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 0, 0))  # force update
    qtbot.waitUntil(lambda: plot_item.pois[0].mouseHovering)
    qtbot.mouseDClick(
        plot.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ShiftModifier,
        pos=data_to_screen(plot_item, 0.1, 1),
    )  # make sure we can't double-create

    qtbot.mouseClick(plot.viewport(), Qt.MouseButton.LeftButton, pos=data_to_screen(plot_item, 0, 0))  # force capture
    qtbot.keyClick(plot.viewport(), Qt.Key.Key_Delete)
    qtbot.waitUntil(lambda: len(plot_item.pois) == 0)
