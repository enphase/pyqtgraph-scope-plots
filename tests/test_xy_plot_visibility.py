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

from pyqtgraph_scope_plots import VisibilityXyPlotWidget, VisibilityXyPlotTable
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget
from pyqtgraph_scope_plots.visibility_toggle_table import VisibilityDataStateModel


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
    qtbot.waitUntil(lambda: cast(VisibilityDataStateModel, plot._dump_model()).hidden == [])

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
