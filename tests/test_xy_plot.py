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
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.plots_table_widget import PlotsTableWidget
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget


@pytest.fixture()
def plot(qtbot: QtBot) -> PlotsTableWidget:
    """Creates a signals plot with multiple data items"""
    plot = PlotsTableWidget()
    plot._set_data_items(
        [
            ("0", QColor("yellow"), MultiPlotWidget.PlotType.DEFAULT),
            ("1", QColor("orange"), MultiPlotWidget.PlotType.DEFAULT),
            ("2", QColor("blue"), MultiPlotWidget.PlotType.DEFAULT),
        ]
    )
    plot._set_data(
        {
            "0": ([0, 1, 2], [0, 1, 2]),
            "1": ([0, 1, 2], [2, 1, 0]),
            "2": ([1, 2, 3], [0, 1, 2]),  # offset in time but evenly spaced
            "X": ([0, 1, 4], [0, 1, 2]),  # not evenly spaced
        }
    )
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    return plot


def test_xy_create(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    # test that xy creation doesn't error out and follows the user order
    plot._table.item(1, 0).setSelected(True)
    plot._table.item(0, 0).setSelected(True)
    xy_plot = plot._table._on_xy()
    assert xy_plot is not None
    assert xy_plot._xys == [("1", "0")]

    plot._table.clearSelection()
    plot._table.item(0, 0).setSelected(True)
    plot._table.item(1, 0).setSelected(True)
    xy_plot = plot._table._on_xy()
    assert xy_plot is not None
    assert xy_plot._xys == [("0", "1")]

    qtbot.wait(10)  # wait for rendering to happen


def test_xy_offset(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    plot._table.item(0, 0).setSelected(True)
    plot._table.item(2, 0).setSelected(True)
    xy_plot = plot._table._on_xy()
    assert xy_plot is not None
    assert xy_plot._xys == [("0", "2")]

    xy_plot.add_xy("2", "0")
    assert xy_plot._xys == [("0", "2"), ("2", "0")]

    qtbot.wait(10)  # wait for rendering to happen
