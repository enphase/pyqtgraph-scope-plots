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
import time
from unittest import mock

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
    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads


def test_load_sparse_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_sparse.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads


def test_load_multiple_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csv(
        [
            os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv"),
            os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_diffcols.csv"),
        ]
    )
    qtbot.waitUntil(lambda: plot._plots.count() == 4)


def test_append_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)
    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_diffcols.csv")], append=True)
    qtbot.waitUntil(lambda: plot._plots.count() == 4)  # test that the new data is appended


def test_watch_stability(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)
    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csv") as mock_load_csv, mock.patch.object(
        os.path, "getmtime"
    ) as mock_getmtime:
        mock_getmtime.return_value = time.time() - 10  # unchanged file
        plot._watch_timer.timeout.emit()
        qtbot.wait(10)  # add a delay for the call to happen just in case
        mock_load_csv.assert_not_called()

        mock_getmtime.return_value = mock_getmtime.return_value + 10  # reset the counter
        plot._watch_timer.timeout.emit()
        qtbot.waitUntil(lambda: mock_load_csv.called)  # check the load happens


def test_save_model_csvs(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    # test empty save
    model = plot._do_save_config(os.path.join(os.path.dirname(__file__), "config.yml"))
    assert model.csv_files == []  # relpath

    plot._load_csv([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])

    # test saving in relpath mode
    model = plot._do_save_config(os.path.join(os.path.dirname(__file__), "config.yml"))
    assert model.csv_files == [os.path.join("data", "test_csv_viewer_data.csv")]  # relpath

    # test saving in abspath mode
    model = plot._do_save_config("/lol/config.yml")
    assert model.csv_files == [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv"))
    ]


def test_load_model_csvs_relpath(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    model = plot._do_save_config("/config.yml")

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csv") as mock_load_csv:
        model.csv_files = None
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_not_called()

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csv") as mock_load_csv:
        model.csv_files = [os.path.join("data", "test_csv_viewer_data.csv")]  # relpath
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_called_with(
            [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")], update=False
        )

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csv") as mock_load_csv:
        model.csv_files = [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")]  # abspath
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_called_with(
            [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")], update=False
        )
