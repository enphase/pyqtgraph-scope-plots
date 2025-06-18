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

import pytest
from PySide6.QtGui import QColor, Qt
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import MultiPlotWidget, VisibilityXyPlotWidget, VisibilityXyPlotTable, XyTable
from pyqtgraph_scope_plots.util.util import not_none
from pyqtgraph_scope_plots.xy_plot_table import XyTableStateModel
from pyqtgraph_scope_plots.xy_plot_visibility import XyVisibilityStateModel
from .common_testdata import DATA_ITEMS, XY_DATA


@pytest.fixture()
def plot(qtbot: QtBot) -> VisibilityXyPlotWidget:
    plots = MultiPlotWidget()
    plots.show_data_items(DATA_ITEMS)
    plots.set_data(XY_DATA)
    xy_plot = VisibilityXyPlotWidget(plots)
    xy_plot.add_xy("0", "1")
    qtbot.addWidget(xy_plot)
    xy_plot.show()
    qtbot.waitExposed(xy_plot)
    return xy_plot


def test_visibility(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    assert plot._xy_curves[("0", "1")][0].isVisible()

    plot.hide_xys([("0", "1")])
    assert not plot._xy_curves[("0", "1")][0].isVisible()

    plot.hide_xys([("0", "1")], hidden=False)
    assert plot._xy_curves[("0", "1")][0].isVisible()


def test_visibility_table(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    table = VisibilityXyPlotTable(plot._plots, plot)
    table._update()

    table.item(0, table.COL_VISIBILITY).setCheckState(Qt.CheckState.Unchecked)
    assert not plot._xy_curves[("0", "1")][0].isVisible()

    table.item(0, table.COL_VISIBILITY).setCheckState(Qt.CheckState.Checked)
    assert plot._xy_curves[("0", "1")][0].isVisible()


def test_visibility_save(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    assert cast(XyVisibilityStateModel, plot._dump_model()).hidden_data == []

    plot.hide_xys([("0", "1")])
    assert cast(XyVisibilityStateModel, plot._dump_model()).hidden_data == [("0", "1")]


def test_visibility_load(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    table = VisibilityXyPlotTable(plot._plots, plot)
    table._update()
    model = cast(XyVisibilityStateModel, plot._dump_model())

    model.hidden_data = [("0", "1")]
    plot._load_model(model)
    table._update()  # trigger update
    assert table.item(0, table.COL_VISIBILITY).checkState() == Qt.CheckState.Unchecked

    model.hidden_data = []
    plot._load_model(model)
    table._update()  # trigger update
    assert table.item(0, table.COL_VISIBILITY).checkState() == Qt.CheckState.Checked


class XyTableWithMixins(XyTable):
    _XY_PLOT_TYPE = VisibilityXyPlotWidget


def test_toptable_composition(qtbot: QtBot) -> None:
    """Test that the top-level dump (from the timeseries table) models are composed properly
    including hidden_data from VisibilityXyPlotWidget"""
    plots = MultiPlotWidget()
    table = XyTableWithMixins(plots)
    table.create_xy()
    top_model = cast(XyTableStateModel, table._dump_data_model([]))
    assert cast(XyVisibilityStateModel, not_none(top_model.xy_windows)[0]).hidden_data == []
    assert top_model.model_dump()["xy_windows"][0]["hidden_data"] == []  # validation to schema happens here
