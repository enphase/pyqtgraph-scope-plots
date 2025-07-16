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


from pyqtgraph_scope_plots import LinkedMultiPlotWidget, StatsSignalsTable
from pyqtgraph_scope_plots.stats_signals_table import StatsTableStateModel
from .common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def table(qtbot: QtBot) -> StatsSignalsTable:
    """Creates a signals plot with multiple data items"""
    plots = LinkedMultiPlotWidget()
    table = StatsSignalsTable(plots)
    plots.show_data_items(DATA_ITEMS)
    plots.set_data(DATA)
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)
    return table


def test_full_range(qtbot: QtBot, table: StatsSignalsTable) -> None:
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_MIN).text()) == 0
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_MAX).text()) == 1
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_AVG).text()) == pytest.approx(0.5025, 0.01)
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_RMS).text()) == pytest.approx(0.707, 0.01)
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_STDEV).text()) == pytest.approx(0.4975, 0.01)

    qtbot.waitUntil(lambda: table.item(1, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(1, table.COL_STAT + table.COL_STAT_MIN).text()) == 0.25
    assert float(table.item(1, table.COL_STAT + table.COL_STAT_MAX).text()) == 0.5
    assert float(table.item(1, table.COL_STAT + table.COL_STAT_AVG).text()) == pytest.approx(0.4166, 0.01)
    assert float(table.item(1, table.COL_STAT + table.COL_STAT_RMS).text()) == pytest.approx(0.4330, 0.01)
    assert float(table.item(1, table.COL_STAT + table.COL_STAT_STDEV).text()) == pytest.approx(0.1178, 0.01)

    qtbot.waitUntil(lambda: table.item(2, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MIN).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MAX).text()) == 0.7
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_AVG).text()) == pytest.approx(0.6, 0.01)
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_RMS).text()) == pytest.approx(0.6055, 0.01)
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_STDEV).text()) == pytest.approx(0.0816, 0.01)


def test_region(qtbot: QtBot, table: StatsSignalsTable) -> None:
    plots = table._plots
    assert isinstance(plots, LinkedMultiPlotWidget)
    plots._on_region_change(None, (0.5, 2.5))
    qtbot.waitUntil(lambda: table.item(2, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MIN).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MAX).text()) == 0.6
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_AVG).text()) == pytest.approx(0.55, 0.01)
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_RMS).text()) == pytest.approx(0.5522, 0.01)
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_STDEV).text()) == pytest.approx(0.05, 0.01)


def test_region_single(qtbot: QtBot, table: StatsSignalsTable) -> None:
    plots = table._plots
    assert isinstance(plots, LinkedMultiPlotWidget)
    plots._on_region_change(None, (1.5, 2.5))
    qtbot.waitUntil(lambda: table.item(2, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MIN).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_MAX).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_AVG).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_RMS).text()) == 0.5
    assert float(table.item(2, table.COL_STAT + table.COL_STAT_STDEV).text()) == 0.0


def test_region_empty(qtbot: QtBot, table: StatsSignalsTable) -> None:
    plots = table._plots
    assert isinstance(plots, LinkedMultiPlotWidget)
    plots._on_region_change(None, (2.5, 1000))
    qtbot.wait(10)
    assert table.item(2, table.COL_STAT + table.COL_STAT_MIN).text() == ""
    assert table.item(2, table.COL_STAT + table.COL_STAT_MAX).text() == ""
    assert table.item(2, table.COL_STAT + table.COL_STAT_AVG).text() == ""
    assert table.item(2, table.COL_STAT + table.COL_STAT_RMS).text() == ""
    assert table.item(2, table.COL_STAT + table.COL_STAT_STDEV).text() == ""


def test_disable_enable(qtbot: QtBot, table: StatsSignalsTable) -> None:
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() != "")

    table.disable_stats(True)
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() == "")
    for row in [0, 1, 2]:
        for col in table.STATS_COLS:
            assert table.item(row, table.COL_STAT + col).text() == ""

    table.disable_stats(False)
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() != "")


def test_stats_table_save(qtbot: QtBot, table: StatsSignalsTable) -> None:
    assert cast(StatsTableStateModel, table._dump_data_model([])).stats_disabled == False

    table.disable_stats(True)
    assert cast(StatsTableStateModel, table._dump_data_model([])).stats_disabled == True

    table.disable_stats(False)
    assert cast(StatsTableStateModel, table._dump_data_model([])).stats_disabled == False


def test_stats_table_load(qtbot: QtBot, table: StatsSignalsTable) -> None:
    model = cast(StatsTableStateModel, table._dump_data_model([]))

    model.stats_disabled = True
    table._load_model(model)
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() == "")

    model.stats_disabled = False
    table._load_model(model)
    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() != "")
