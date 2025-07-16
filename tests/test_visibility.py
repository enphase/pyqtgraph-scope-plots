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
from PySide6.QtGui import Qt
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import VisibilityPlotWidget, VisibilityToggleSignalsTable
from pyqtgraph_scope_plots.visibility_toggle_table import VisibilityDataStateModel
from .common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def visibility_plots(qtbot: QtBot) -> VisibilityPlotWidget:
    """Creates a signals plot with multiple data items"""
    plots = VisibilityPlotWidget()
    plots.show_data_items(DATA_ITEMS)
    plots.set_data(DATA)
    qtbot.addWidget(plots)
    plots.show()
    qtbot.waitExposed(plots)
    return plots


def test_visibility(qtbot: QtBot, visibility_plots: VisibilityPlotWidget) -> None:
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert visibility_plots._data_curves["1"][0].isVisible()
    assert visibility_plots._data_curves["2"][0].isVisible()

    visibility_plots.hide_data_items(["1"])
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert not visibility_plots._data_curves["1"][0].isVisible()
    assert visibility_plots._data_curves["2"][0].isVisible()

    visibility_plots.hide_data_items(["2", "0"])
    assert not visibility_plots._data_curves["0"][0].isVisible()
    assert not visibility_plots._data_curves["1"][0].isVisible()
    assert not visibility_plots._data_curves["2"][0].isVisible()

    visibility_plots.hide_data_items(["0"], hidden=False)
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert not visibility_plots._data_curves["1"][0].isVisible()
    assert not visibility_plots._data_curves["2"][0].isVisible()

    visibility_plots.set_data(DATA)  # visibility status should be retained across data set
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert not visibility_plots._data_curves["1"][0].isVisible()
    assert not visibility_plots._data_curves["2"][0].isVisible()


def test_visibility_table(qtbot: QtBot, visibility_plots: VisibilityPlotWidget) -> None:
    visibility_table = VisibilityToggleSignalsTable(visibility_plots)
    visibility_table._update()
    visibility_table.item(1, visibility_table.COL_VISIBILITY).setCheckState(Qt.CheckState.Unchecked)
    qtbot.waitUntil(lambda: not visibility_plots._data_curves["1"][0].isVisible())
    assert visibility_plots._data_curves["0"][0].isVisible()  # check unchanged
    assert visibility_plots._data_curves["2"][0].isVisible()

    visibility_table.item(1, visibility_table.COL_VISIBILITY).setCheckState(Qt.CheckState.Checked)
    qtbot.waitUntil(lambda: visibility_plots._data_curves["1"][0].isVisible())
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert visibility_plots._data_curves["2"][0].isVisible()


def test_visibility_save(qtbot: QtBot, visibility_plots: VisibilityPlotWidget) -> None:
    visibility_plots.hide_data_items(["1"])
    model = visibility_plots._dump_data_model(["0", "1", "2"])
    assert cast(VisibilityDataStateModel, model.data["0"]).hidden == False
    assert cast(VisibilityDataStateModel, model.data["1"]).hidden == True
    assert cast(VisibilityDataStateModel, model.data["2"]).hidden == False


def test_visibility_load(qtbot: QtBot, visibility_plots: VisibilityPlotWidget) -> None:
    visibility_table = VisibilityToggleSignalsTable(visibility_plots)
    model = visibility_plots._dump_data_model(["0", "1", "2"])
    cast(VisibilityDataStateModel, model.data["1"]).hidden = True

    visibility_plots._load_model(model)
    visibility_plots.set_data(DATA)  # trigger a curve-visibility update
    visibility_table._update()  # trigger update
    assert visibility_plots._data_curves["0"][0].isVisible()
    assert not visibility_plots._data_curves["1"][0].isVisible()
    assert visibility_plots._data_curves["2"][0].isVisible()

    assert visibility_table.item(0, visibility_table.COL_VISIBILITY).checkState() == Qt.CheckState.Checked
    assert visibility_table.item(1, visibility_table.COL_VISIBILITY).checkState() == Qt.CheckState.Unchecked
    assert visibility_table.item(2, visibility_table.COL_VISIBILITY).checkState() == Qt.CheckState.Checked
