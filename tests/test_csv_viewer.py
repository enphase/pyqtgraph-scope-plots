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

import os

import pytest
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.csv.csv_plots import CsvLoaderPlotsTableWidget


@pytest.fixture()
def plot(qtbot: QtBot) -> CsvLoaderPlotsTableWidget:
    """Creates a signals plot with multiple data items"""
    plot = CsvLoaderPlotsTableWidget()
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    return plot


def test_load_mixed_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    new_plot = plot._load_csv(os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv"))
    qtbot.waitUntil(lambda: new_plot._plots.count() == 3)  # just make sure it loads


def test_load_sparse_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    new_plot = plot._load_csv(os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_sparse.csv"))
    qtbot.waitUntil(lambda: new_plot._plots.count() == 3)  # just make sure it loads
