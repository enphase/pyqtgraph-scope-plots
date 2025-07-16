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
import pytest
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotStateModel, PlotWidgetModel
from pyqtgraph_scope_plots import MultiPlotWidget, DroppableMultiPlotWidget, SignalsTable
from tests.common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def plots(qtbot: QtBot) -> DroppableMultiPlotWidget:
    """Creates a signals plot with multiple data items"""
    plots = DroppableMultiPlotWidget()
    plots.show_data_items(DATA_ITEMS)
    plots.set_data(DATA)
    qtbot.addWidget(plots)
    plots.show()
    qtbot.waitExposed(plots)
    return plots


def test_plot_merge(qtbot: QtBot, plots: DroppableMultiPlotWidget) -> None:
    table = SignalsTable(plots)
    table._update()

    qtbot.waitUntil(lambda: plots.count() == 3)  # wait for plots to be ready

    plots._merge_data_into_item(["0"], 1)  # merge
    qtbot.waitUntil(lambda: plots.count() == 2)  # wait for widgets to merge
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 2
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(1)).getPlotItem()).listDataItems()) == 1
    assert table.rowCount() == 3  # signals table should not change
    assert table.item(0, table.COL_NAME).text() == "0"
    assert table.item(1, table.COL_NAME).text() == "1"
    assert table.item(2, table.COL_NAME).text() == "2"

    plots._merge_data_into_item(["0"], 1)  # move
    qtbot.waitUntil(lambda: plots.count() == 2)
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 1
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(1)).getPlotItem()).listDataItems()) == 2
    assert table.rowCount() == 3  # signals table should not change
    assert table.item(0, table.COL_NAME).text() == "0"
    assert table.item(1, table.COL_NAME).text() == "1"
    assert table.item(2, table.COL_NAME).text() == "2"

    plots._merge_data_into_item(["1"], 1)  # merge all
    qtbot.waitUntil(lambda: plots.count() == 1)
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 3
    assert table.rowCount() == 3  # signals table should not change
    assert table.item(0, table.COL_NAME).text() == "0"
    assert table.item(1, table.COL_NAME).text() == "1"
    assert table.item(2, table.COL_NAME).text() == "2"

    plots._merge_data_into_item(["2"], 0, insert=True)  # insert at top
    qtbot.waitUntil(lambda: plots.count() == 2)  # new plot created
    assert table.rowCount() == 3  # signals table should not change
    assert table.item(0, table.COL_NAME).text() == "0"
    assert table.item(1, table.COL_NAME).text() == "1"
    assert table.item(2, table.COL_NAME).text() == "2"

    plots._merge_data_into_item(["0"], 2, insert=True)  # insert at bottom
    qtbot.waitUntil(lambda: plots.count() == 3)


def test_plot_merge_multi(qtbot: QtBot, plots: DroppableMultiPlotWidget) -> None:
    qtbot.waitUntil(lambda: plots.count() == 3)  # wait for plots to be ready

    plots._merge_data_into_item(["0", "1"], 0)  # merge into self, including self
    qtbot.waitUntil(lambda: plots.count() == 2)  # wait for widgets to merge
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 2
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(1)).getPlotItem()).listDataItems()) == 1

    plots._merge_data_into_item(["0", "1"], 1)  # merge into other, not including self
    qtbot.waitUntil(lambda: plots.count() == 1)  # wait for widgets to merge
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 3

    plots._merge_data_into_item(["1", "2"], 2, insert=True)  # insert at bottom
    qtbot.waitUntil(lambda: plots.count() == 2)
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 1
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(1)).getPlotItem()).listDataItems()) == 2

    plots._merge_data_into_item(["0", "1", "2"], 2, insert=True)  # insert all
    qtbot.waitUntil(lambda: plots.count() == 1)
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 3


def test_invalid_plot_merge(qtbot: QtBot, plots: DroppableMultiPlotWidget) -> None:
    plots.show_data_items(
        DATA_ITEMS
        + [
            ("3", QColor("cyan"), MultiPlotWidget.PlotType.ENUM_WAVEFORM),
            ("4", QColor("brown"), MultiPlotWidget.PlotType.ENUM_WAVEFORM),
        ]
    )

    qtbot.waitUntil(lambda: plots.count() == 5)  # wait for plots to be ready

    plots._merge_data_into_item(["3"], 0)  # invalid merge, different types
    plots._merge_data_into_item(["0"], 3)  # invalid merge, different types
    plots._merge_data_into_item(["3"], 4)  # can't merge enums
    plots._merge_data_into_item(["4"], 3)  # can't merge enums

    assert plots.count() == 5  # check nothing changes


def test_plot_remove(qtbot: QtBot, plots: DroppableMultiPlotWidget) -> None:
    plots.remove_plot_items(["1"])
    qtbot.waitUntil(lambda: plots.count() == 2)  # plot removed

    plots._merge_data_into_item(["2"], 0)  # merge all into top
    qtbot.waitUntil(lambda: plots.count() == 1)
    assert len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 2

    plots.remove_plot_items(["0"])
    qtbot.waitUntil(
        lambda: len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 1
    )

    plots.remove_plot_items(["2"])  # delete the last plot, the empty plot should appear
    qtbot.waitUntil(
        lambda: len(cast(pg.PlotItem, cast(pg.PlotWidget, plots.widget(0)).getPlotItem()).listDataItems()) == 0
    )


def test_plot_save(qtbot: QtBot, plots: DroppableMultiPlotWidget) -> None:
    qtbot.waitUntil(
        lambda: cast(MultiPlotStateModel, plots._dump_data_model([])).plot_widgets
        == [
            PlotWidgetModel(data_items=["0"], y_range="auto"),
            PlotWidgetModel(data_items=["1"], y_range="auto"),
            PlotWidgetModel(data_items=["2"], y_range="auto"),
        ]
    )

    plots._merge_data_into_item(["0"], 1)  # merge
    qtbot.waitUntil(
        lambda: cast(MultiPlotStateModel, plots._dump_data_model([])).plot_widgets
        == [PlotWidgetModel(data_items=["1", "0"], y_range="auto"), PlotWidgetModel(data_items=["2"], y_range="auto")]
    )

    plots._merge_data_into_item(["2"], 0)  # merge
    qtbot.waitUntil(
        lambda: cast(MultiPlotStateModel, plots._dump_data_model([])).plot_widgets
        == [PlotWidgetModel(data_items=["1", "0", "2"], y_range="auto")]
    )
