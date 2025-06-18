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

from pyqtgraph_scope_plots import MultiPlotWidget, SearchSignalsTable


@pytest.fixture()
def search_table(qtbot: QtBot) -> SearchSignalsTable:
    """Creates a signals plot with multiple data items"""
    plots = MultiPlotWidget()
    table = SearchSignalsTable(plots)
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


def test_search_empty(qtbot: QtBot, search_table: SearchSignalsTable) -> None:
    search = search_table._on_find()
    assert search.isVisible()


def test_search_nomatch(qtbot: QtBot, search_table: SearchSignalsTable) -> None:
    search = search_table._on_find()
    search._search_input.setText("ducks")
    search._search_input.textEdited.emit("ducks")
    qtbot.waitUntil(lambda: search._results.text().lower() == "no matches")

    # make sure prev / next don't crash
    search._prev_button.clicked.emit()
    search._next_button.clicked.emit()
    qtbot.wait(10)
    assert not search_table.selectedItems()


def test_search_single(qtbot: QtBot, search_table: SearchSignalsTable) -> None:
    search = search_table._on_find()
    search._search_input.setText("aaa")
    search._search_input.textEdited.emit("aaa")
    qtbot.waitUntil(lambda: search._results.text().lower() == "1 matches")

    # make sure prev / next do the right thing
    search._prev_button.clicked.emit()
    qtbot.wait(10)
    assert [item.row() for item in search_table.selectedItems()] == [0]
    search._next_button.clicked.emit()
    qtbot.wait(10)
    assert [item.row() for item in search_table.selectedItems()] == [0]


def test_search_case_insensitive(qtbot: QtBot, search_table: SearchSignalsTable) -> None:
    search = search_table._on_find()
    search._search_input.setText("ABc")
    search._search_input.textEdited.emit("ABc")
    qtbot.waitUntil(lambda: [item.row() for item in search_table.selectedItems()] == [1])


def test_search_multiple(qtbot: QtBot, search_table: SearchSignalsTable) -> None:
    search = search_table._on_find()
    search._search_input.setText("b")
    search._search_input.textEdited.emit("b")
    qtbot.waitUntil(lambda: search._results.text().lower() == "2 matches")
    qtbot.waitUntil(lambda: [item.row() for item in search_table.selectedItems()] == [1])

    # check next/prev navigation works
    search._prev_button.clicked.emit()
    qtbot.waitUntil(lambda: [item.row() for item in search_table.selectedItems()] == [2])  # wraparound
    search._next_button.clicked.emit()
    qtbot.waitUntil(lambda: [item.row() for item in search_table.selectedItems()] == [1])  # wraparound
