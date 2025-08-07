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
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.csv.csv_plots import CsvLoaderPlotsTableWidget, CsvLoaderRecents
from tests.util import MockQSettings, menu_action_by_name


@pytest.fixture()
def plot(qtbot: QtBot) -> CsvLoaderPlotsTableWidget:
    """Creates a signals plot with multiple data items"""
    plot = CsvLoaderPlotsTableWidget()
    qtbot.addWidget(plot)
    plot.show()
    qtbot.waitExposed(plot)
    return plot


def test_load_mixed_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads


def test_load_sparse_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_sparse.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads


def test_load_multiple_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csvs(
        [
            os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv"),
            os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_diffcols.csv"),
        ]
    )
    qtbot.waitUntil(lambda: plot._plots.count() == 4)


def test_append_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)
    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data_diffcols.csv")], append=True)
    qtbot.waitUntil(lambda: plot._plots.count() == 4)  # test that the new data is appended


def test_watch_stability(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])
    qtbot.waitUntil(lambda: plot._plots.count() == 3)
    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csvs") as mock_load_csv, mock.patch.object(
        os.path, "getmtime"
    ) as mock_getmtime:
        mock_getmtime.return_value = time.time() - 10  # unchanged file
        plot._watch_timer.timeout.emit()
        qtbot.wait(10)  # add a delay for the call to happen just in case
        mock_load_csv.assert_not_called()

        mock_getmtime.return_value = mock_getmtime.return_value + 10  # reset the counter
        plot._watch_timer.timeout.emit()
        qtbot.waitUntil(lambda: mock_load_csv.called)  # check the load happens


@mock.patch.object(CsvLoaderPlotsTableWidget, "_config", lambda *args: MockQSettings())
def test_save_model_csvs(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    # test empty save
    model = plot._do_save_config(os.path.join(os.path.dirname(__file__), "config.yml"))
    assert model.csv_files == []  # relpath

    plot._load_csvs([os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")])

    # test saving in relpath mode
    model = plot._do_save_config(os.path.join(os.path.dirname(__file__), "config.yml"))
    assert model.csv_files == [os.path.join("data", "test_csv_viewer_data.csv")]  # relpath

    # test saving in abspath mode
    model = plot._do_save_config("/lol/config.yml")
    assert model.csv_files == [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv"))
    ]


@mock.patch.object(CsvLoaderPlotsTableWidget, "_config", lambda *args: MockQSettings())
def test_load_model_csvs_relpath(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    model = plot._do_save_config("/config.yml")

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csvs") as mock_load_csv:
        model.csv_files = None
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_not_called()

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csvs") as mock_load_csv:
        model.csv_files = [os.path.join("data", "test_csv_viewer_data.csv")]  # relpath
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_called_with(
            [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")], update=False
        )

    with mock.patch.object(CsvLoaderPlotsTableWidget, "_load_csvs") as mock_load_csv:
        model.csv_files = [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")]  # abspath
        plot._do_load_config(os.path.join(os.path.dirname(__file__), "config.yml"), model)
        mock_load_csv.assert_called_with(
            [os.path.join(os.path.dirname(__file__), "data", "test_csv_viewer_data.csv")], update=False
        )


def test_recents_save(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    settings = MockQSettings()
    with mock.patch.object(CsvLoaderPlotsTableWidget, "_config", lambda *args: settings):
        assert plot._get_recents() == CsvLoaderRecents()
        model = plot._do_save_config("/config.yml")  # stores to recents
        assert plot._get_recents().recents == [os.path.abspath("/config.yml")]

        plot._do_load_config(os.path.join(os.path.dirname(__file__), "test.yml"), model)
        assert plot._get_recents().recents == [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "test.yml")),
            os.path.abspath("/config.yml"),
        ]

        # check reordering latest-first + dedup
        plot._do_load_config("/config.yml", model)
        assert plot._get_recents().recents == [
            os.path.abspath("/config.yml"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "test.yml")),
        ]

        # check pruning
        for i in range(10):
            plot._do_load_config(f"/extra{i}.yml", model)
        assert len(plot._get_recents().recents) == 9

        # check hotkeys
        with mock.patch.object(QInputDialog, "getInt", lambda *args, **kwargs: (8, True)):
            plot._on_set_hotkey()
        assert plot._get_recents().hotkeys[8] == os.path.abspath(f"/extra9.yml")
        assert len(plot._get_recents().recents) == 8
        assert os.path.abspath(f"/extra9.yml") not in plot._get_recents().recents
        assert os.path.abspath(f"/extra8.yml") in plot._get_recents().recents

        # check most recent pruned
        plot._do_load_config(f"/extra11.yml", model)
        assert plot._get_recents().hotkeys[8] == os.path.abspath(f"/extra9.yml")
        assert len(plot._get_recents().recents) == 8
        assert os.path.abspath(f"/extra0.yml") not in plot._get_recents().recents
        assert os.path.abspath(f"/extra11.yml") in plot._get_recents().recents

        # check that it is possible to max out the hotkey range
        for i in range(10):
            plot._do_load_config(f"/extra{i}.yml", model)
            with mock.patch.object(QInputDialog, "getInt", lambda *args, **kwargs: (i, True)):
                plot._on_set_hotkey()
        assert len(plot._get_recents().recents) == 0

        # recents no longer saves, hotkeys take priority
        plot._do_load_config(f"/extra11.yml", model)
        assert len(plot._get_recents().recents) == 0


@mock.patch.object(CsvLoaderPlotsTableWidget, "load_config_file")
def test_recents_load(mock_load_config: mock.MagicMock, qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    settings = MockQSettings()
    with mock.patch.object(CsvLoaderPlotsTableWidget, "_config", lambda *args: settings):
        plot._populate_config_menu()
        assert len(plot._menu_config.actions()) == 4  # 2 empty items + separators

        qtbot.keyClick(plot, Qt.Key.Key_4, modifier=Qt.KeyboardModifier.ControlModifier)  # check nothing happens

        plot._do_save_config("/config.yml")  # stores to recents
        plot._populate_config_menu()
        assert len(plot._menu_config.actions()) == 5
        load_action = menu_action_by_name(plot._menu_config, "config.yml")
        assert load_action is not None
        load_action.trigger()
        mock_load_config.assert_called_once_with(os.path.abspath("/config.yml"))
        mock_load_config.reset_mock()

        # set and test hotkey
        with mock.patch.object(QInputDialog, "getInt", lambda *args, **kwargs: (4, True)):
            plot._on_set_hotkey()
        qtbot.keyClick(plot, Qt.Key.Key_4, modifier=Qt.KeyboardModifier.ControlModifier)
        mock_load_config.assert_called_once_with(os.path.abspath("/config.yml"))
