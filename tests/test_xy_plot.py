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

import numpy as np
import pytest
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import MultiPlotWidget, XyPlotWidget, XyWindowModel, XyPlotSplitter, XyTable
from pyqtgraph_scope_plots.xy_plot_table import XyTableStateModel
from pyqtgraph_scope_plots.util.util import not_none

from .common_testdata import DATA_ITEMS, XY_DATA


@pytest.fixture()
def xy_table(qtbot: QtBot) -> XyTable:
    """Creates a signals plot with multiple data items"""
    table = XyTable(MultiPlotWidget())
    table._plots.show_data_items(DATA_ITEMS)
    table._plots.set_data(XY_DATA)
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)
    return table


def test_correlated_indices() -> None:
    assert XyPlotWidget._get_correlated_indices(np.array([0, 1, 2, 3]), np.array([0, 1, 2, 3]), 0, 2) == (
        (0, 3),
        (0, 3),
    )
    assert XyPlotWidget._get_correlated_indices(np.array([0, 10, 20, 30]), np.array([0, 10, 20, 30]), 0, 20) == (
        (0, 3),
        (0, 3),
    )

    # test different alignments
    assert XyPlotWidget._get_correlated_indices(np.array([-10, 0, 10, 20, 30]), np.array([0, 10, 20, 30]), 0, 20) == (
        (1, 4),
        (0, 3),
    )
    assert XyPlotWidget._get_correlated_indices(np.array([0, 10, 20, 30]), np.array([-10, 0, 10, 20, 30]), 0, 20) == (
        (0, 3),
        (1, 4),
    )

    # test tiny offset
    assert XyPlotWidget._get_correlated_indices(
        np.array([0, 10 + 1e-5, 20 - 1e-5, 30]), np.array([0, 10, 20, 30]), 0, 20
    ) == (
        (0, 3),
        (0, 3),
    )

    # test excess offset
    assert XyPlotWidget._get_correlated_indices(np.array([0, 11, 20, 30]), np.array([0, 10, 20, 30]), 0, 20) is None
    assert XyPlotWidget._get_correlated_indices(np.array([0, 20, 30]), np.array([0, 10, 20, 30]), 0, 20) is None


def test_xy_create_ui(qtbot: QtBot, xy_table: XyTable) -> None:
    # test that xy creation doesn't error out and follows the user order
    xy_table.item(1, 0).setSelected(True)
    xy_table.item(0, 0).setSelected(True)
    xy_plot = cast(XyPlotSplitter, xy_table._on_create_xy())
    qtbot.waitSignal(xy_plot._xy_plots.sigXyDataItemsChanged)
    assert xy_plot is not None
    assert xy_plot._xy_plots._xys == [("1", "0")]

    xy_table.clearSelection()
    xy_table.item(0, 0).setSelected(True)
    xy_table.item(1, 0).setSelected(True)
    xy_plot = cast(XyPlotSplitter, xy_table._on_create_xy())
    qtbot.waitSignal(xy_plot._xy_plots.sigXyDataItemsChanged)
    assert xy_plot is not None
    assert xy_plot._xy_plots._xys == [("0", "1")]

    qtbot.wait(10)  # wait for rendering to happen


def test_xy_close_cleanup(qtbot: QtBot, xy_table: XyTable) -> None:
    xy_plot = cast(XyPlotSplitter, xy_table.create_xy())
    xy_plot.add_xy("0", "2")
    qtbot.waitUntil(lambda: len(xy_table._xy_plots) > 0)
    xy_plot.close()
    qtbot.waitUntil(lambda: not xy_table._xy_plots)


def test_xy_offset(qtbot: QtBot, xy_table: XyTable) -> None:
    xy_plot = cast(XyPlotSplitter, xy_table.create_xy())
    xy_plot.add_xy("0", "2")
    xy_plot.add_xy("2", "0")
    assert xy_plot._xy_plots._xys == [("0", "2"), ("2", "0")]

    qtbot.wait(10)  # wait for rendering to happen to ensure it doesn't error


def test_xy_save(qtbot: QtBot, xy_table: XyTable) -> None:
    xy_plot = xy_table.create_xy()
    xy_plot.add_xy("0", "1")
    xy_plot.add_xy("1", "0")
    qtbot.waitUntil(lambda: len(not_none(cast(XyTableStateModel, xy_table._dump_data_model([])).xy_windows)) == 1)
    model = cast(XyTableStateModel, xy_table._dump_data_model([]))
    assert not_none(model.xy_windows)[0].xy_data_items == [("0", "1"), ("1", "0")]


def test_xy_load(qtbot: QtBot, xy_table: XyTable) -> None:
    model = cast(XyTableStateModel, xy_table._dump_data_model([]))

    model.xy_windows = [XyWindowModel(xy_data_items=[("1", "0")])]
    xy_table._load_model(model)
    qtbot.waitUntil(lambda: len(xy_table._xy_plots) == 1)
    assert cast(XyPlotSplitter, xy_table._xy_plots[0])._xy_plots._xys == [("1", "0")]


def test_xy_table(qtbot: QtBot, xy_table: XyTable) -> None:
    xy_plot = cast(XyPlotSplitter, xy_table.create_xy())
    xy_plot.add_xy("0", "1")
    qtbot.waitUntil(lambda: xy_plot._table.rowCount() == 1)
    assert xy_plot._table.item(0, 0).text() == "0"
    assert xy_plot._table.item(0, 1).text() == "1"

    xy_plot.add_xy("1", "0")
    qtbot.waitUntil(lambda: xy_plot._table.rowCount() == 2)
    assert xy_plot._table.item(0, 0).text() == "0"
    assert xy_plot._table.item(0, 1).text() == "1"
    assert xy_plot._table.item(1, 0).text() == "1"
    assert xy_plot._table.item(1, 1).text() == "0"
