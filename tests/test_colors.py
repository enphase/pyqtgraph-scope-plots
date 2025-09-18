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
from unittest import mock

import pytest
from PySide6.QtGui import Qt, QPen, QColor
import pyqtgraph as pg
from PySide6.QtWidgets import QColorDialog
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots import (
    VisibilityPlotWidget,
    VisibilityToggleSignalsTable,
    ColorPickerPlotWidget,
    ColorPickerSignalsTable,
)
from pyqtgraph_scope_plots.color_signals_table import ColorPickerDataStateModel
from pyqtgraph_scope_plots.visibility_toggle_table import VisibilityDataStateModel
from .common_testdata import DATA_ITEMS, DATA


@pytest.fixture()
def color_plots(qtbot: QtBot) -> ColorPickerPlotWidget:
    """Creates a signals plot with multiple data items"""
    plots = ColorPickerPlotWidget()
    plots.show_data_items(DATA_ITEMS)
    plots.set_data(DATA)
    qtbot.addWidget(plots)
    plots.show()
    qtbot.waitExposed(plots)
    return plots


def color_of_curve(curve: pg.PlotCurveItem) -> QColor:
    return cast(QPen, curve.opts["pen"]).color()


def test_color(qtbot: QtBot, color_plots: ColorPickerPlotWidget) -> None:
    color_plots.set_colors(["1"], QColor("indigo"))
    assert color_of_curve(color_plots._data_name_to_plot_item["1"]._data_graphics["1"][0]) == QColor("indigo")

    # rest should not have changed
    assert color_of_curve(color_plots._data_name_to_plot_item["0"]._data_graphics["0"][0]) == QColor("yellow")
    assert color_of_curve(color_plots._data_name_to_plot_item["2"]._data_graphics["2"][0]) == QColor("blue")


def test_color_table(qtbot: QtBot, color_plots: ColorPickerPlotWidget) -> None:
    color_table = ColorPickerSignalsTable(color_plots)

    # test API => table
    color_plots.set_colors(["1"], QColor("goldenrod"))
    assert color_table.item(1, 0).foreground().color() == QColor("goldenrod")

    # test table UI => table
    with mock.patch.object(QColorDialog, "getColor", lambda: QColor("lavender")):
        color_table.selectRow(1)
        color_table._on_set_color()
    assert color_of_curve(color_plots._data_name_to_plot_item["1"]._data_graphics["1"][0]) == QColor("lavender")
    assert color_table.item(1, 0).foreground().color() == QColor("lavender")


def test_color_save(qtbot: QtBot, color_plots: ColorPickerPlotWidget) -> None:
    color_plots.set_colors(["1"], QColor("goldenrod"))
    model = color_plots._dump_data_model(["0", "1", "2"])

    assert cast(ColorPickerDataStateModel, model.data["0"]).color is None
    assert cast(ColorPickerDataStateModel, model.data["1"]).color == QColor("goldenrod")
    assert cast(ColorPickerDataStateModel, model.data["2"]).color is None


def test_color_load(qtbot: QtBot, color_plots: ColorPickerPlotWidget) -> None:
    color_table = ColorPickerSignalsTable(color_plots)
    model = color_plots._dump_data_model(["0", "1", "2"])
    cast(ColorPickerDataStateModel, model.data["1"]).color = QColor("goldenrod")

    color_plots._load_model(model)
    color_plots.show_data_items(DATA_ITEMS)  # trigger a colors update
    color_table._update()  # trigger update
    assert color_of_curve(color_plots._data_name_to_plot_item["1"]._data_graphics["1"][0]) == QColor("goldenrod")
    assert color_table.item(1, 0).foreground().color() == QColor("goldenrod")
