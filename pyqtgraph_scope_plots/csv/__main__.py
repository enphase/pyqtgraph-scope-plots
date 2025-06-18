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

"""Basic demonstration of the interactive plots and tables in a standalone app that provides default
synthetic data and also can load CSVs."""

import math

import numpy as np
from PySide6 import QtGui
from PySide6.QtWidgets import QApplication

from .csv_plots import CsvLoaderPlotsTableWidget
from ..multi_plot_widget import MultiPlotWidget
from ..util import int_color


class CsvLoaderPlotsTableWindow(CsvLoaderPlotsTableWidget):
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        QApplication.closeAllWindows()
        event.accept()


if __name__ == "__main__":
    app = QApplication([])
    plots = CsvLoaderPlotsTableWindow()
    plots.resize(1200, 800)

    PTS_PER_CYCLE = 128
    X_PER_CYCLE = 1.0
    CYCLES = 4

    plots._set_data_items(
        [
            ("sine", int_color(0), MultiPlotWidget.PlotType.DEFAULT),
            ("square", int_color(1), MultiPlotWidget.PlotType.DEFAULT),
            ("cycle", int_color(2), MultiPlotWidget.PlotType.ENUM_WAVEFORM),
            ("step", int_color(3), MultiPlotWidget.PlotType.DEFAULT),
        ]
    )

    xs = np.linspace(0, X_PER_CYCLE * CYCLES, PTS_PER_CYCLE * CYCLES, endpoint=False)
    plots._set_data(
        {
            "sine": (xs, np.sin(xs / X_PER_CYCLE * 2 * math.pi)),
            "square": (xs, np.signbit(np.sin(xs / X_PER_CYCLE * 2 * math.pi)).astype(float)),
            "cycle": (
                xs,
                [f"Cycle {int(x)}" for x in np.floor(xs / X_PER_CYCLE)],
            ),
            "step": (xs, np.floor(xs / X_PER_CYCLE)),
        }
    )

    plots.show()
    app.exec()
