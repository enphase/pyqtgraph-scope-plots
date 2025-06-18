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
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import VisibilityXyPlotWidget, VisibilityXyPlotTable, XyTable
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget
from pyqtgraph_scope_plots.visibility_toggle_table import VisibilityDataStateModel
from pyqtgraph_scope_plots.xy_plot_table import XyTableStateModel


@pytest.fixture()
def plot(qtbot: QtBot) -> VisibilityXyPlotWidget:
    xy_plot = VisibilityXyPlotWidget(MultiPlotWidget())
    qtbot.addWidget(xy_plot)
    xy_plot.show()
    qtbot.waitExposed(xy_plot)
    return xy_plot


def test_visibility(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    pass


def test_visibility_table(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    pass


def test_visibility_save(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    qtbot.waitUntil(lambda: cast(VisibilityDataStateModel, plot._dump_model()).hidden_data == [])

    # TODO
    # plot.set_ref_geometry_fn("([-1, 1], [-1, -1])")
    # qtbot.waitUntil(lambda: cast(XyRefGeoModel, plot._dump_model()).ref_geo == ["([-1, 1], [-1, -1])"])


def test_visibility_load(qtbot: QtBot, plot: VisibilityXyPlotWidget) -> None:
    table = VisibilityXyPlotTable(plot._plots, plot)
    model = cast(VisibilityDataStateModel, plot._dump_model())

    # TODO
    # model.ref_geo = ["([-1, 1], [-1, -1])"]
    # plot._load_model(model)
    # qtbot.waitUntil(lambda: table.rowCount() == 1)
    # assert table.item(0, 0).text() == "([-1, 1], [-1, -1])"
    #
    # model.ref_geo = []
    # plot._load_model(model)
    # qtbot.waitUntil(lambda: table.rowCount() == 0)


class XyTableWithMixins(XyTable):
    _XY_PLOT_TYPE = VisibilityXyPlotWidget


def test_toptable_composition(qtbot: QtBot) -> None:
    """Test that the top-level dump (from the timeseries table) models are composed properly
    including hidden_data from VisibilityXyPlotWidget"""
    plots = MultiPlotWidget()
    table = XyTableWithMixins(plots)
    table.create_xy()
    top_model = cast(XyTableStateModel, table._dump_data_model([]))
    assert cast(VisibilityDataStateModel, top_model.xy_windows[0]).hidden_data == []
    assert top_model.model_dump()["xy_windows"][0]["hidden_data"] == []  # validation to schema happens here
