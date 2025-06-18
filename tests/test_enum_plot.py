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
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from pyqtgraph import PlotWidget
from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.multi_plot_widget import EnumWaveformInteractivePlot
from pyqtgraph_scope_plots.util.util import not_none


@pytest.fixture()
def plot(qtbot: QtBot) -> PlotWidget:
    """Creates a signals plot with multiple data items"""
    plot = EnumWaveformInteractivePlot()
    plot.update_plot("0", QColor("yellow"), [0, 1, 1.5, 2, 6, 7, 7.4], ["A", "B", "B", "B", "C", "A", "A"])
    widget = PlotWidget(plotItem=plot)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_empty_one(qtbot: QtBot, plot: PlotWidget) -> None:
    plot_item = cast(EnumWaveformInteractivePlot, plot.plotItem)
    plot_item.update_plot("0", QColor("grey"), [], [])

    plot_item.update_plot("0", QColor("grey"), [0], ["test"])
    plot_item.update_plot("0", QColor("grey"), [1], ["test"])


def test_labels(qtbot: QtBot, plot: PlotWidget) -> None:
    plot_item = cast(EnumWaveformInteractivePlot, plot.plotItem)
    qtbot.waitUntil(lambda: len(plot_item._curves_labels) == 2)
    assert plot_item._curves_labels[0].toPlainText() == "B"  # longest segment
    assert plot_item._curves_labels[1].toPlainText() == "A"  # short segment but past end

    plot_item.update_plot("0", QColor("grey"), [0, 1], ["test", "test"])  # test unchanging waveform
    assert len(plot_item._curves_labels) == 1
    assert plot_item._curves_labels[0].toPlainText() == "test"


def test_snap(qtbot: QtBot, plot: PlotWidget) -> None:
    plot_item = cast(EnumWaveformInteractivePlot, plot.plotItem)
    assert not_none(plot_item._snap_pos(QPointF(0, 0), 0, 10)) == QPointF(0, 0)  # exact snap
    assert not_none(plot_item._snap_pos(QPointF(7.4, 0), 0, 10)) == QPointF(7.4, 0)  # exact at noninteger
    assert not_none(plot_item._snap_pos(QPointF(6, 0), 0, 10)) == QPointF(6, 0)
    assert not_none(plot_item._snap_pos(QPointF(6, 100), 0, 10)) == QPointF(6, 0)  # discard y

    assert not_none(plot_item._snap_pos(QPointF(1.5, 100), 0, 10)) == QPointF(1, 0)  # prefer edges
    assert not_none(plot_item._snap_pos(QPointF(1.5, 100), 1.1, 1.9)) == QPointF(1.5, 0)  # ... within window

    assert plot_item._snap_pos(QPointF(1.5, 100), 0.1, 0.9) is None


def test_data_values(qtbot: QtBot, plot: PlotWidget) -> None:
    plot_item = cast(EnumWaveformInteractivePlot, plot.plotItem)
    assert plot_item._data_value_label_at(0) == [(0, "A", QColor("yellow"))]
    assert plot_item._data_value_label_at(1.5) == [(0, "B", QColor("yellow"))]
    assert plot_item._data_value_label_at(1.6) == []
    assert plot_item._data_value_label_at(7.4) == [(0, "A", QColor("yellow"))]
