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
from unittest import mock

import pytest
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot
import pyqtgraph as pg

from pyqtgraph_scope_plots.xy_plot_splitter import XyPlotSplitter
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget, LinkedMultiPlotWidget
from pyqtgraph_scope_plots.xy_plot_refgeo import RefGeoXyPlotWidget, XyRefGeoModel


@pytest.fixture()
def plot(qtbot: QtBot) -> RefGeoXyPlotWidget:
    xy_plot = RefGeoXyPlotWidget(LinkedMultiPlotWidget())
    qtbot.addWidget(xy_plot)
    xy_plot.show()
    qtbot.waitExposed(xy_plot)
    return xy_plot


@pytest.fixture()
def splitter(qtbot: QtBot) -> XyPlotSplitter:
    splitter = XyPlotSplitter(LinkedMultiPlotWidget())
    qtbot.addWidget(splitter)
    splitter.show()
    qtbot.waitExposed(splitter)
    return splitter


def test_square_points(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    with mock.patch.object(plot, "addItem") as mock_add_item:
        plot.set_ref_geometry_fn("([-1, 1, 1, -1, -1], [-1, -1, 1, 1, -1])")
        mock_add_item.assert_called_once()
        curve = cast(pg.PlotCurveItem, mock_add_item.call_args[0][0])
        assert list(curve.xData) == [-1, 1, 1, -1, -1]
        assert list(curve.yData) == [-1, -1, 1, 1, -1]


def test_polyline_fn(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    with mock.patch.object(plot, "addItem") as mock_add_item:
        plot.set_ref_geometry_fn("polyline((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))")
        mock_add_item.assert_called_once()
        curve = cast(pg.PlotCurveItem, mock_add_item.call_args[0][0])
        assert list(curve.xData) == [-1, 1, 1, -1, -1]
        assert list(curve.yData) == [-1, -1, 1, 1, -1]


def test_data(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    plot._plots.show_data_items([("x", QColor("white"), MultiPlotWidget.PlotType.DEFAULT)])
    plot._plots.set_data({"x": ([0, 1, 2], [0, 1, 2])})

    with mock.patch.object(plot, "addItem") as mock_add_item:
        plot.set_ref_geometry_fn("polyline((-1, data['x'][-1]), (1, data['x'][-1]))")
        mock_add_item.assert_called_once()
        curve = cast(pg.PlotCurveItem, mock_add_item.call_args[0][0])
        assert list(curve.xData) == [-1, 1]
        assert list(curve.yData) == [2, 2]

    with mock.patch.object(plot, "addItem") as mock_add_item:
        plot.set_ref_geometry_fn("polyline((-1, data['x'][-1]), (1, data['x'][0]))", 0)
        mock_add_item.assert_called_once()
        curve = cast(pg.PlotCurveItem, mock_add_item.call_args[0][0])
        assert list(curve.xData) == [-1, 1]
        assert list(curve.yData) == [2, 0]


def test_data_region(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    plot._plots.show_data_items([("x", QColor("white"), MultiPlotWidget.PlotType.DEFAULT)])
    plot._plots.set_data({"x": ([0, 1, 2], [0, 1, 2])})
    cast(LinkedMultiPlotWidget, plot._plots)._on_region_change(None, (0, 1))

    with mock.patch.object(plot, "addItem") as mock_add_item:
        plot.set_ref_geometry_fn("polyline((-1, data['x'][0]), (1, data['x'][-1]))")
        mock_add_item.assert_called_once()
        curve = cast(pg.PlotCurveItem, mock_add_item.call_args[0][0])
        assert list(curve.xData) == [-1, 1]
        assert list(curve.yData) == [0, 1]


def test_table(qtbot: QtBot, splitter: XyPlotSplitter) -> None:
    splitter._xy_plots.set_ref_geometry_fn("([-1, 1], [-1, -1])")
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 1)
    assert splitter._table.item(0, 0).text() == "([-1, 1], [-1, -1])"

    splitter._xy_plots.set_ref_geometry_fn("([-1, 2], [-1, -1])")  # addition
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 2)
    assert splitter._table.item(0, 0).text() == "([-1, 1], [-1, -1])"
    assert splitter._table.item(1, 0).text() == "([-1, 2], [-1, -1])"

    splitter._xy_plots.set_ref_geometry_fn("([-1, 0], [-1, -1])", 1)  # replacement
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 2)
    assert splitter._table.item(0, 0).text() == "([-1, 1], [-1, -1])"
    assert splitter._table.item(1, 0).text() == "([-1, 0], [-1, -1])"

    splitter._xy_plots.set_ref_geometry_fn("", 0)  # deletion
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 1)
    assert splitter._table.item(0, 0).text() == "([-1, 0], [-1, -1])"


def test_table_err(qtbot: QtBot, splitter: XyPlotSplitter) -> None:
    splitter._xy_plots.set_ref_geometry_fn("abc")
    qtbot.waitUntil(lambda: "NameNotDefined" in splitter._table.item(0, 0).text())


def test_refgeo_save(qtbot: QtBot, splitter: XyPlotSplitter) -> None:
    qtbot.waitUntil(lambda: cast(XyRefGeoModel, splitter._dump_model()).ref_geo == [])

    splitter._xy_plots.set_ref_geometry_fn("([-1, 1], [-1, -1])")
    qtbot.waitUntil(lambda: cast(XyRefGeoModel, splitter._dump_model()).ref_geo == ["([-1, 1], [-1, -1])"])


def test_refgeo_load(qtbot: QtBot, splitter: XyPlotSplitter) -> None:
    model = cast(XyRefGeoModel, splitter._dump_model())

    model.ref_geo = ["([-1, 1], [-1, -1])"]
    splitter._load_model(model)
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 1)
    assert splitter._table.item(0, 0).text() == "([-1, 1], [-1, -1])"

    model.ref_geo = []
    splitter._load_model(model)
    qtbot.waitUntil(lambda: splitter._table.rowCount() == 0)
