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

from typing import List
import numpy as np
import numpy.typing as npt

from PySide6.QtGui import QColor

from pyqtgraph_scope_plots import MultiPlotWidget


def np_immutable(x: List[float]) -> npt.NDArray[np.float64]:
    """Creates a np.array with immutable set (writable=False)"""
    arr = np.array(x)
    arr.flags.writeable = False
    return arr


DATA_ITEMS = [
    ("0", QColor("yellow"), MultiPlotWidget.PlotType.DEFAULT),
    ("1", QColor("orange"), MultiPlotWidget.PlotType.DEFAULT),
    ("2", QColor("blue"), MultiPlotWidget.PlotType.DEFAULT),
]

DATA = {
    "0": (np_immutable([0, 0.1, 1, 2]), np_immutable([0.01, 1, 1, 0])),
    "1": (np_immutable([0, 1, 2]), np_immutable([0.5, 0.25, 0.5])),
    "2": (np_immutable([0, 1, 2]), np_immutable([0.7, 0.6, 0.5])),
}

XY_DATA = {
    "0": ([0, 1, 2], [0, 1, 2]),
    "1": ([0, 1, 2], [2, 1, 0]),
    "2": ([1, 2, 3], [0, 1, 2]),  # offset in time but evenly spaced
    "X": ([0, 1, 4], [0, 1, 2]),  # not evenly spaced
}
