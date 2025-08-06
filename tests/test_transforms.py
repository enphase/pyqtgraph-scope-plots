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

from typing import Tuple, Any, cast
from unittest import mock

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QInputDialog
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import MultiPlotWidget, TransformsSignalsTable, TransformsPlotWidget
from pyqtgraph_scope_plots.code_input_dialog import CodeInputDialog
from pyqtgraph_scope_plots.transforms_signal_table import TransformsDataStateModel
from pyqtgraph_scope_plots.util.util import not_none
from .common_testdata import DATA
from .util import context_menu, menu_action_by_name


@pytest.fixture()
def transforms_plots(qtbot: QtBot) -> TransformsPlotWidget:
    """Creates a signals plot with multiple data items"""
    plots = TransformsPlotWidget()
    plots.show_data_items(
        [
            ("0", QColor("yellow"), MultiPlotWidget.PlotType.DEFAULT),
            ("1", QColor("orange"), MultiPlotWidget.PlotType.DEFAULT),
            ("2", QColor("blue"), MultiPlotWidget.PlotType.DEFAULT),
        ]
    )
    plots.set_data(DATA)
    qtbot.addWidget(plots)
    plots.show()
    qtbot.waitExposed(plots)
    return plots


def test_transform_empty(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Tests empty transforms, should return the input"""
    assert transforms_plots._apply_transform("0", DATA).tolist() == [0.01, 1, 1, 0]
    assert transforms_plots._apply_transform("1", DATA).tolist() == [0.5, 0.25, 0.5]
    assert transforms_plots._apply_transform("2", DATA).tolist() == [0.7, 0.6, 0.5]


def test_transform_x(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Tests transforms that only reference x"""
    transforms_plots.set_transform(["0"], "x + 1")
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [1.01, 2, 2, 1])

    transforms_plots.set_transform(["1"], "x * 2")
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("1", DATA).tolist() == [1, 0.5, 1])
    assert transforms_plots._apply_transform("0", DATA).tolist() == [1.01, 2, 2, 1]  # should not affect 0

    transforms_plots.set_transform(["0"], "")
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [0.01, 1, 1, 0])
    assert transforms_plots._apply_transform("1", DATA).tolist() == [1, 0.5, 1]


def test_transform_multiple(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Tests transforms that reference other data objects"""
    transforms_plots.set_transform(["1"], "x + data['2']")
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("1", DATA).tolist() == [1.2, 0.85, 1])

    transforms_plots.set_transform(["1"], "x + data['0']")  # allow getting with longer data
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("1", DATA).tolist() == [0.51, 1.25, 0.5])

    transforms_plots.set_transform(["0"], "x + data.get('1', 0)")  # test .get with missing values
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [0.51, 1, 1.25, 0.5])


def test_transform_ui(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Basic test of transforms driven from the UI"""
    transforms_table = TransformsSignalsTable(transforms_plots)
    transforms_table._update()
    target = transforms_table.visualItemRect(
        not_none(transforms_table.item(1, transforms_table.COL_TRANSFORM))
    ).center()
    with mock.patch.object(CodeInputDialog, "getText") as mock_input:  # allow getting with longer data
        mock_input.return_value = ("x + data['0']", True)
        menu_action_by_name(context_menu(qtbot, transforms_table, target), "set function").trigger()
        qtbot.waitUntil(lambda: transforms_plots._apply_transform("1", DATA).tolist() == [0.51, 1.25, 0.5])


def test_transform_ui_syntaxerror(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Tests that syntax errors repeatedly prompt"""
    transforms_table = TransformsSignalsTable(transforms_plots)
    transforms_table._update()
    target = transforms_table.visualItemRect(
        not_none(transforms_table.item(0, transforms_table.COL_TRANSFORM))
    ).center()
    with mock.patch.object(CodeInputDialog, "getText") as mock_input:  # test error on missing values
        mock_value = ("is", True)  # Python keyword, invalid syntax

        def mock_value_update(*args: Any, **kwargs: Any) -> Tuple[str, bool]:
            nonlocal mock_value
            prev_mock_value = mock_value
            mock_value = ("1", True)
            return prev_mock_value

        mock_input.side_effect = mock_value_update
        menu_action_by_name(context_menu(qtbot, transforms_table, target), "set function").trigger()
        qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [1, 1, 1, 1])


def test_transform_ui_error(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    transforms_table = TransformsSignalsTable(transforms_plots)
    transforms_table._update()
    target = transforms_table.visualItemRect(
        not_none(transforms_table.item(0, transforms_table.COL_TRANSFORM))
    ).center()
    with mock.patch.object(CodeInputDialog, "getText") as mock_input:  # test error on missing values
        mock_input.return_value = ("ducks", True)
        menu_action_by_name(context_menu(qtbot, transforms_table, target), "set function").trigger()
        qtbot.waitUntil(lambda: isinstance(transforms_plots._apply_transform("0", DATA), Exception))  # must evaluate
        qtbot.waitUntil(lambda: "NameNotDefined" in transforms_table.item(0, transforms_table.COL_TRANSFORM).text())

    with mock.patch.object(CodeInputDialog, "getText") as mock_input:  # test error on missing values
        mock_input.return_value = ("x + data['1']", True)
        menu_action_by_name(context_menu(qtbot, transforms_table, target), "set function").trigger()
        qtbot.waitUntil(lambda: isinstance(transforms_plots._apply_transform("0", DATA), Exception))  # must evaluate
        qtbot.waitUntil(lambda: "KeyError" in transforms_table.item(0, transforms_table.COL_TRANSFORM).text())

    with mock.patch.object(CodeInputDialog, "getText") as mock_input:  # test error on missing values
        mock_input.return_value = ("'ducks'", True)
        menu_action_by_name(context_menu(qtbot, transforms_table, target), "set function").trigger()
        qtbot.waitUntil(lambda: isinstance(transforms_plots._apply_transform("0", DATA), Exception))  # must evaluate
        qtbot.waitUntil(lambda: "TypeError" in transforms_table.item(0, transforms_table.COL_TRANSFORM).text())


def test_transform_save(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    assert cast(TransformsDataStateModel, transforms_plots._dump_data_model(["0", "1"]).data["0"]).transform == ""
    assert cast(TransformsDataStateModel, transforms_plots._dump_data_model(["0", "1"]).data["1"]).transform == ""

    transforms_plots.set_transform(["1"], "x + data['0']")  # allow getting with longer data
    qtbot.waitUntil(
        lambda: cast(TransformsDataStateModel, transforms_plots._dump_data_model(["0", "1"]).data["1"]).transform
        == "x + data['0']"
    )
    assert (
        cast(TransformsDataStateModel, transforms_plots._dump_data_model(["0", "1"]).data["0"]).transform == ""
    )  # unchanged


def test_transform_load(qtbot: QtBot, transforms_plots: TransformsPlotWidget) -> None:
    """Tests transforms that only reference x"""
    model = transforms_plots._dump_data_model(["0"])

    cast(TransformsDataStateModel, model.data["0"]).transform = "x + 1"
    transforms_plots._load_model(model)
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [1.01, 2, 2, 1])

    cast(TransformsDataStateModel, model.data["0"]).transform = ""
    transforms_plots._load_model(model)
    qtbot.waitUntil(lambda: transforms_plots._apply_transform("0", DATA).tolist() == [0.01, 1, 1, 0])
