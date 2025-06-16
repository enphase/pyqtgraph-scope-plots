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

from pyqtgraph_scope_plots import StatsSignalsTable
from pyqtgraph_scope_plots.multi_plot_widget import MultiPlotWidget
from .test_transforms import DATA


@pytest.fixture()
def table(qtbot: QtBot) -> StatsSignalsTable:
    """Creates a signals plot with multiple data items"""
    plots = MultiPlotWidget()
    table = StatsSignalsTable(plots)
    plots.show_data_items(
        [
            ("0", QColor("yellow"), MultiPlotWidget.PlotType.DEFAULT),
            ("1", QColor("orange"), MultiPlotWidget.PlotType.DEFAULT),
            ("2", QColor("blue"), MultiPlotWidget.PlotType.DEFAULT),
        ]
    )
    plots.set_data(DATA)
    qtbot.addWidget(table)
    table.show()
    qtbot.waitExposed(table)
    return table


def test_full_range(qtbot: QtBot, table: StatsSignalsTable) -> None:
    qtbot.waitUntil(lambda: table.rowCount() == 3)

    qtbot.waitUntil(lambda: table.item(0, table.COL_STAT + table.COL_STAT_MIN).text() != "")
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_MIN).text()) == 0
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_MAX).text()) == 1
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_AVG).text()) == 0.5025
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_RMS).text()) == pytest.approx(0.707, 0.01)
    assert float(table.item(0, table.COL_STAT + table.COL_STAT_STDEV).text()) == pytest.approx(0, 0.01)  # TODO
