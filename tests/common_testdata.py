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
