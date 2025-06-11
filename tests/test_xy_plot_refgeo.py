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

import pytest
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import XyPlotSplitter
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget
from pyqtgraph_scope_plots.xy_plot_refgeo import RefGeoXyPlotWidget


@pytest.fixture()
def plot(qtbot: QtBot) -> RefGeoXyPlotWidget:
    xy_plot = RefGeoXyPlotWidget(MultiPlotWidget())
    qtbot.addWidget(xy_plot)
    xy_plot.show()
    qtbot.waitExposed(xy_plot)
    return xy_plot


def test_square_points(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    # test that xy creation doesn't error out and follows the user order
    plot.add_xy("0", "1")
    plot.add_ref_geometry_fn("([-1, 1, 1, -1, -1], [-1, -1, 1, 1, -1])")
    qtbot.wait(10)  # wait for rendering to happen


def test_polyline_fn(qtbot: QtBot, plot: RefGeoXyPlotWidget) -> None:
    # test that xy creation doesn't error out and follows the user order
    plot.add_xy("0", "1")
    plot.add_ref_geometry_fn("polyline((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))")
    qtbot.wait(10)  # wait for rendering to happen


def test_table(qtbot: QtBot):
    splitter = XyPlotSplitter(MultiPlotWidget())
    qtbot.addWidget(splitter)
    splitter.show()
    qtbot.waitExposed(splitter)

    splitter._xy_plots.add_ref_geometry_fn("([-1, 1], [-1, -1])")
    qtbot.waitUntil(lambda: splitter._table.item(0, 0).text() == "([-1, 1], [-1, -1])")
