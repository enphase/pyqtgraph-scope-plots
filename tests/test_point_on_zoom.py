# Copyright 2026 Enphase Energy, Inc.
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

import numpy as np
import pyqtgraph as pg
import pytest
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.point_on_zoom_plot import PointOnZoomPlot
from .common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def point_plot(qtbot: QtBot) -> tuple[PointOnZoomPlot, pg.PlotWidget]:
    plot_item = PointOnZoomPlot()
    widget = pg.PlotWidget(plotItem=plot_item)
    widget.setFixedSize(160, 120)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    plot_item.set_data_items({name: color for name, color, _ in DATA_ITEMS})
    return plot_item, widget


def _scatter_len(plot_item: PointOnZoomPlot, name: str) -> int:
    return len(plot_item._point_scatters[name].getData()[0])


def test_zoomed_in_visible(qtbot: QtBot, point_plot: tuple[PointOnZoomPlot, pg.PlotWidget]) -> None:
    plot_item, _ = point_plot
    plot_item.set_data({"0": DATA["0"]})
    plot_item.getViewBox().setXRange(0, 0.2, padding=0)

    qtbot.waitUntil(lambda: plot_item._point_scatters["0"].isVisible())
    assert _scatter_len(plot_item, "0") > 0


def test_zoomed_out_hidden(qtbot: QtBot, point_plot: tuple[PointOnZoomPlot, pg.PlotWidget]) -> None:
    plot_item, _ = point_plot
    plot_item.set_data({"0": DATA["0"]})
    plot_item.getViewBox().setXRange(-5, 25, padding=0)

    qtbot.waitUntil(lambda: not plot_item._point_scatters["0"].isVisible())
    # note: scatter plot data does not get cleared


def test_zoom_change(qtbot: QtBot, point_plot: tuple[PointOnZoomPlot, pg.PlotWidget]) -> None:
    plot_item, _ = point_plot
    plot_item.set_data({"0": DATA["0"]})
    plot_item.getViewBox().setXRange(0, 0.2, padding=0)
    qtbot.waitUntil(lambda: plot_item._point_scatters["0"].isVisible())
    assert _scatter_len(plot_item, "0") > 0

    plot_item.getViewBox().setXRange(-5, 25, padding=0)
    qtbot.waitUntil(lambda: not plot_item._point_scatters["0"].isVisible())

    plot_item.getViewBox().setXRange(0, 0.2, padding=0)
    qtbot.waitUntil(lambda: plot_item._point_scatters["0"].isVisible())
    assert _scatter_len(plot_item, "0") > 0


def test_single_point(qtbot: QtBot, point_plot: tuple[PointOnZoomPlot, pg.PlotWidget]) -> None:
    plot_item, _ = point_plot
    plot_item.set_data({"0": (np.array([1.0]), np.array([2.0]))})
    plot_item.getViewBox().setXRange(0, 2, padding=0)

    qtbot.waitUntil(lambda: plot_item._point_scatters["0"].isVisible())
    assert _scatter_len(plot_item, "0") == 1


def test_empty_data(qtbot: QtBot, point_plot: tuple[PointOnZoomPlot, pg.PlotWidget]) -> None:
    plot_item, _ = point_plot
    plot_item.getViewBox().setXRange(-1, 1, padding=0)
    plot_item.set_data({"0": (np.array([], dtype=float), np.array([], dtype=float))})

    qtbot.waitUntil(lambda: not plot_item._point_scatters["0"].isVisible())
    assert _scatter_len(plot_item, "0") == 0
