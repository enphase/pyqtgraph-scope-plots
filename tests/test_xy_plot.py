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

from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.plots_table_widget import PlotsTableWidget
from .test_base_plot import plot


def test_xy_create(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    # test that xy creation doesn't error out and follows the user order
    # use items 1 and 2 since they share the same indices
    plot._table.item(2, 0).setSelected(True)
    plot._table.item(1, 0).setSelected(True)
    xy_plot = plot._table._on_xy()
    assert xy_plot is not None
    assert xy_plot._xys == [("2", "1")]

    plot._table.clearSelection()
    plot._table.item(1, 0).setSelected(True)
    plot._table.item(2, 0).setSelected(True)
    xy_plot = plot._table._on_xy()
    assert xy_plot is not None
    assert xy_plot._xys == [("1", "2")]
