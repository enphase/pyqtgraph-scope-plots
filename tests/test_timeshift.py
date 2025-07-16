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

from pyqtgraph_scope_plots import TimeshiftSignalsTable, TimeshiftPlotWidget
from pyqtgraph_scope_plots.timeshift_signals_table import TimeshiftDataStateModel
from .common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def timeshifts_plots(qtbot: QtBot) -> TimeshiftPlotWidget:
    """Creates a signals plot with multiple data items"""
    plots = TimeshiftPlotWidget()
    plots.show_data_items(DATA_ITEMS)
    qtbot.addWidget(plots)
    plots.show()
    qtbot.waitExposed(plots)
    return plots


def test_timeshift(qtbot: QtBot, timeshifts_plots: TimeshiftPlotWidget) -> None:
    timeshifts_table = TimeshiftSignalsTable(timeshifts_plots)
    timeshifts_table._update()
    # test empty
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [0.0, 0.1, 1.0, 2.0])
    timeshifts_plots.set_timeshift(["0"], 1)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [1.0, 1.1, 2.0, 3.0])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == "1"
    timeshifts_plots.set_timeshift(["0"], -0.5)  # test negative and noninteger
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [-0.5, -0.4, 0.5, 1.5])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == "-0.5"
    timeshifts_plots.set_timeshift(["0"], 0)  # revert to empty
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [0.0, 0.1, 1.0, 2.0])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == ""


def test_timeshift_table(qtbot: QtBot, timeshifts_plots: TimeshiftPlotWidget) -> None:
    timeshifts_table = TimeshiftSignalsTable(timeshifts_plots)
    timeshifts_table._update()
    timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).setText("1")
    timeshifts_table.cellChanged.emit(0, timeshifts_table.COL_TIMESHIFT)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [1.0, 1.1, 2.0, 3.0])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == "1.0"
    timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).setText("-0.5")  # test negative and noninteger
    timeshifts_table.cellChanged.emit(0, timeshifts_table.COL_TIMESHIFT)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [-0.5, -0.4, 0.5, 1.5])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == "-0.5"
    timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).setText("")
    timeshifts_table.cellChanged.emit(0, timeshifts_table.COL_TIMESHIFT)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [0.0, 0.1, 1.0, 2.0])
    assert timeshifts_table.item(0, timeshifts_table.COL_TIMESHIFT).text() == ""


def test_timeshift_save(qtbot: QtBot, timeshifts_plots: TimeshiftPlotWidget) -> None:
    qtbot.waitUntil(
        lambda: cast(TimeshiftDataStateModel, timeshifts_plots._dump_data_model(["0"]).data["0"]).timeshift == 0
    )
    timeshifts_plots.set_timeshift(["0"], -0.5)
    qtbot.waitUntil(
        lambda: cast(TimeshiftDataStateModel, timeshifts_plots._dump_data_model(["0"]).data["0"]).timeshift == -0.5
    )


def test_timeshift_load(qtbot: QtBot, timeshifts_plots: TimeshiftPlotWidget) -> None:
    model = timeshifts_plots._dump_data_model(["0"])
    cast(TimeshiftDataStateModel, model.data["0"]).timeshift = -0.5
    timeshifts_plots._load_model(model)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [-0.5, -0.4, 0.5, 1.5])

    cast(TimeshiftDataStateModel, model.data["0"]).timeshift = 0
    timeshifts_plots._load_model(model)
    qtbot.waitUntil(lambda: timeshifts_plots._apply_timeshift("0", DATA).tolist() == [0.0, 0.1, 1.0, 2.0])
