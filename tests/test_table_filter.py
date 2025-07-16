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

from pyqtgraph_scope_plots import MultiPlotWidget, FilterSignalsTable


@pytest.fixture()
def filter_table(qtbot: QtBot) -> FilterSignalsTable:
    """Creates a signals plot with multiple data items"""
    plots = MultiPlotWidget()
    table = FilterSignalsTable(plots)
    plots.show_data_items(
        [
            ("aaa", QColor("yellow"), MultiPlotWidget.PlotType.DEFAULT),
            ("abC", QColor("orange"), MultiPlotWidget.PlotType.DEFAULT),
            ("abd", QColor("blue"), MultiPlotWidget.PlotType.DEFAULT),
        ]
    )
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)
    return table


def test_filter_empty(qtbot: QtBot, filter_table: FilterSignalsTable) -> None:
    filter_tool = filter_table._on_filter()
    assert filter_tool.isVisible()


def test_filter_nomatch(qtbot: QtBot, filter_table: FilterSignalsTable) -> None:
    filter_tool = filter_table._on_filter()
    filter_tool._filter_input.setText("ducks")
    filter_tool._filter_input.textEdited.emit("ducks")
    qtbot.waitUntil(lambda: filter_tool._results.text().lower() == "no matches")
    assert filter_table.isRowHidden(0)
    assert filter_table.isRowHidden(1)
    assert filter_table.isRowHidden(2)


def test_filter_single(qtbot: QtBot, filter_table: FilterSignalsTable) -> None:
    filter_tool = filter_table._on_filter()
    filter_tool._filter_input.setText("aaa")
    filter_tool._filter_input.textEdited.emit("aaa")
    qtbot.waitUntil(lambda: filter_tool._results.text().lower() == "1 matches")
    assert not filter_table.isRowHidden(0)
    assert filter_table.isRowHidden(1)
    assert filter_table.isRowHidden(2)


def test_filter_case_insensitive(qtbot: QtBot, filter_table: FilterSignalsTable) -> None:
    filter_tool = filter_table._on_filter()
    filter_tool._filter_input.setText("ABc")
    filter_tool._filter_input.textEdited.emit("ABc")
    qtbot.waitUntil(lambda: filter_tool._results.text().lower() == "1 matches")
    assert filter_table.isRowHidden(0)
    assert not filter_table.isRowHidden(1)
    assert filter_table.isRowHidden(2)


def test_filter_multiple(qtbot: QtBot, filter_table: FilterSignalsTable) -> None:
    filter_tool = filter_table._on_filter()
    filter_tool._filter_input.setText("b")
    filter_tool._filter_input.textEdited.emit("b")
    qtbot.waitUntil(lambda: filter_tool._results.text().lower() == "2 matches")
    assert filter_table.isRowHidden(0)
    assert not filter_table.isRowHidden(1)
    assert not filter_table.isRowHidden(2)
