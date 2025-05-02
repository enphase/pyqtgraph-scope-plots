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
    plot._load_csv(os.path.join(os.path.dirname(__file__), 'data', 'test_csv_viewer_data.csv'))
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads


def test_load_sparse_csv(qtbot: QtBot, plot: CsvLoaderPlotsTableWidget) -> None:
    plot._load_csv(os.path.join(os.path.dirname(__file__), 'data', 'test_csv_viewer_data_sparse.csv'))
    qtbot.waitUntil(lambda: plot._plots.count() == 3)  # just make sure it loads
