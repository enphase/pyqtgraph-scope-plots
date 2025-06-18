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

from pytestqt.qtbot import QtBot

from pyqtgraph_scope_plots.multi_plot_widget import LinkedMultiPlotStateModel
from pyqtgraph_scope_plots.util.util import not_none
from pyqtgraph_scope_plots import PlotsTableWidget
from .test_base_plot import plot_item, plot


def test_linked_live_cursor(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    """This (and subsequent) tests use internal APIs to set cursor positions and whatnot
    because these APIs are much more reliable than using QtBot mouse actions."""
    for i in range(3):
        assert plot_item(plot, i).hover_cursor is None  # verify initial state

    plot_item(plot, 0).set_live_cursor(0.1)
    qtbot.waitSignal(plot._plots.sigHoverCursorChanged)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 1).hover_cursor).x() == 0.1)
    assert not_none(plot_item(plot, 2).hover_cursor).x() == 0.1

    plot_item(plot, 1).set_live_cursor(None)
    qtbot.waitSignal(plot._plots.sigHoverCursorChanged)
    qtbot.waitUntil(lambda: plot_item(plot, 0).hover_cursor is None)
    assert plot_item(plot, 2).hover_cursor is None


def test_linked_region(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    for i in range(3):
        assert plot_item(plot, i).cursor is None  # verify initial state
        assert plot_item(plot, i).cursor_range is None

    plot_item(plot, 0).set_region((0.1, 1.5))
    qtbot.waitSignal(plot._plots.sigCursorRangeChanged)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 1).cursor_range).getRegion() == (0.1, 1.5))
    assert not_none(plot_item(plot, 2).cursor_range).getRegion() == (0.1, 1.5)
    for i in range(3):
        assert plot_item(plot, i).cursor is None

    plot_item(plot, 1).set_region(1.0)
    qtbot.waitSignal(plot._plots.sigCursorRangeChanged)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 0).cursor).x() == 1.0)
    assert not_none(plot_item(plot, 2).cursor).x() == 1.0
    for i in range(3):
        assert plot_item(plot, i).cursor_range is None


def test_region_save(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    qtbot.waitUntil(lambda: cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([])).region is None)

    plot_item(plot, 0).set_region((0.1, 1.5))
    qtbot.waitUntil(lambda: cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([])).region == (0.1, 1.5))

    plot_item(plot, 1).set_region(1.0)
    qtbot.waitUntil(lambda: cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([])).region == 1.0)


def test_region_restore(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    model = cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([]))

    model.region = (0.1, 1.5)
    plot._plots._load_model(model)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 1).cursor_range).getRegion() == (0.1, 1.5))
    for i in range(3):
        assert not_none(plot_item(plot, i).cursor_range).getRegion() == (0.1, 1.5)
        assert plot_item(plot, i).cursor is None

    model.region = 1.0
    plot._plots._load_model(model)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 0).cursor).x() == 1.0)
    for i in range(3):
        assert plot_item(plot, i).cursor_range is None
        assert not_none(plot_item(plot, i).cursor).x() == 1.0

    model.region = None  # no change
    plot._plots._load_model(model)
    qtbot.wait(10)  # wait for potential unwanted behavior to propagate
    for i in range(3):
        assert not_none(plot_item(plot, i).cursor).x() == 1.0

    model.region = ()
    plot._plots._load_model(model)
    qtbot.waitUntil(lambda: not_none(plot_item(plot, 0).cursor).x() == 1.0)
    for i in range(3):
        assert plot_item(plot, i).cursor_range is None
        assert not_none(plot_item(plot, i).cursor).x() == 1.0


def test_linked_pois(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    for i in range(3):
        assert not plot_item(plot, i).pois  # verify initial state

    plot_item(plot, 0).set_pois([0.1, 1.5])
    qtbot.waitSignal(plot._plots.sigPoiChanged)
    qtbot.waitUntil(lambda: [poi.x() for poi in plot_item(plot, 1).pois] == [0.1, 1.5])
    assert [poi.x() for poi in plot_item(plot, 2).pois] == [0.1, 1.5]


def test_pois_save(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    qtbot.waitUntil(lambda: cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([])).pois == [])

    plot_item(plot, 0).set_pois([0.1, 1.5])
    qtbot.waitUntil(lambda: cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([])).pois == [0.1, 1.5])


def test_pois_restore(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    model = cast(LinkedMultiPlotStateModel, plot._plots._dump_data_model([]))

    model.pois = [0.1, 1.5]
    plot._plots._load_model(model)
    qtbot.waitUntil(lambda: [poi.x() for poi in plot_item(plot, 1).pois] == [0.1, 1.5])

    model.pois = []
    plot._plots._load_model(model)
    qtbot.waitUntil(lambda: [poi.x() for poi in plot_item(plot, 1).pois] == [])


def test_linked_drag_cursor(qtbot: QtBot, plot: PlotsTableWidget) -> None:
    for i in range(3):
        assert plot_item(plot, i).drag_cursor is None  # verify initial state

    plot_item(plot, 0).set_drag_cursor(0.2)
    qtbot.waitSignal(plot._plots.sigDragCursorChanged)
    qtbot.waitUntil(
        lambda: plot_item(plot, 1).drag_cursor is not None and plot_item(plot, 1).drag_cursor.pos().x() == 0.2
    )
    assert plot_item(plot, 1).drag_cursor.pos().x() == 0.2
    assert plot_item(plot, 2).drag_cursor.pos().x() == 0.2
