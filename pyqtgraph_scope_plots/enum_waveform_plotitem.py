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

import bisect
from typing import List, Tuple, Optional, Any, cast

import numpy as np
import numpy.typing as npt
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRect
from PySide6.QtGui import QColor

from .interactivity_mixins import SnappableHoverPlot, HasDataValueAt


class EnumWaveformPlot(SnappableHoverPlot, HasDataValueAt):
    """Plot that takes data as string vs. time and renders as a digital waveform, with transitions when string
    equality changes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._curves: List[pg.PlotCurveItem] = []
        self._curves_labels: List[pg.TextItem] = []
        self._color = QColor("grey")  # default placeholder value that shouldn't get used
        self._data: Optional[Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]] = None  # array[float], array[Any]
        self._edges = np.array([])  # list of x positions of edges, sorted but not necessarily unique

        self.sigXRangeChanged.connect(self._update_plot_labels)

        self.getViewBox().setLimits(yMin=-1.2, yMax=1.2)
        self.sigYRangeChanged.connect(self._forced_y_range)

    def _forced_y_range(self) -> None:
        """Forces the Y range to a constant, since Y scaling doesn't really make sense for a waveform."""
        self.getViewBox().setYRange(-1.2, 1.2)

    def _snap_pos(self, target_pos: QPointF, x_lo: float, x_hi: float) -> Optional[QPointF]:
        # prefer to snap to the nearest edge (either side) if in the window, otherwise the nearest point
        if self._data is None:
            return None
        edges_lo = bisect.bisect_left(self._edges, x_lo)
        edges_hi = bisect.bisect_right(self._edges, x_hi)
        candidate_poss = self._edges[edges_lo:edges_hi]
        if not len(candidate_poss):  # no edges in window, search all points
            xs, ys = self._data
            index_lo = bisect.bisect_left(xs, x_lo)
            index_hi = bisect.bisect_right(xs, x_hi)
            candidate_poss = xs[index_lo:index_hi]
        if len(candidate_poss):
            candidate_dists = [abs(x - target_pos.x()) for x in candidate_poss]
            min_dist_index = np.argmin(candidate_dists)
            return QPointF(candidate_poss[min_dist_index], 0)
        else:
            return None

    def _data_value_label_at(self, pos: float, precision_factor: float = 1.0) -> List[Tuple[float, str, QColor]]:
        if self._data is None:
            return []
        xs, ys = self._data
        index = bisect.bisect_left(xs, pos)
        if index < len(xs) and xs[index] == pos:  # found exact match
            return [(0, str(ys[index]), self._color)]
        else:
            return []

    def update_plot(
        self,
        name: str,
        color: QColor,
        xs: np.typing.ArrayLike,
        ys: np.typing.ArrayLike,
    ) -> None:
        """Updates the plot data, as name -> (color, Xs, state values)"""
        for curve in self._curves:
            self.removeItem(curve)
        self._color = color
        self._curves = []
        xs = np.array(xs)
        ys_np = np.array(ys)
        self._data = (xs, ys_np)

        # generate the control points for half of the waveform using numpy operations for efficiency
        ys_np = np.array(ys)
        ys_values, ys_int = np.unique(ys_np, return_inverse=True)  # map to integer for efficiency
        # do change detection to find edges, element is true if it is different from the next element
        if len(ys_np):
            changes = np.not_equal(ys_int, np.append(ys_int[1:], ys_int[-1]))
        else:  # handle empty array case
            changes = np.array([])

        changes_indices = np.where(changes)[0]
        # interleave the indices and itself plus one to get all the points where the curve changes
        # note, this may result in duplicate points, which is fine for plotting
        changes_prechanges_indices = (
            np.column_stack(
                (
                    changes_indices,
                    changes_indices + np.ones(len(changes_indices), dtype=int),
                )
            ).reshape(-1)
        ).astype(int)
        heights = np.array(
            ([1, -1, -1, 1] * ((len(changes_prechanges_indices) + 3) // 4))[: len(changes_prechanges_indices)]
        )
        # append first and last elements to pad out the trace
        if len(changes_prechanges_indices):
            changes_prechanges_indices = np.insert(changes_prechanges_indices, 0, 0)
            changes_prechanges_indices = np.append(changes_prechanges_indices, len(xs) - 1)
            heights = np.insert(heights, 0, heights[0])
            heights = np.append(heights, heights[-1])
        elif not len(changes_prechanges_indices) and len(ys_np):  # special case for waveform that doesn't change
            changes_prechanges_indices = np.array([0, len(xs) - 1])
            heights = np.array([1, 1])

        self._edges = np.take(xs, changes_prechanges_indices)

        curve_true = pg.PlotCurveItem(x=self._edges, y=heights, name=name)
        curve_true.setPen(color=color, width=1)
        self.addItem(curve_true)
        curve_comp = pg.PlotCurveItem(x=self._edges, y=np.zeros(len(heights)) - heights)
        curve_comp.setPen(color=color, width=1)
        self.addItem(curve_comp)
        self._curves = [curve_true, curve_comp]

        self._update_plot_labels()

    def resizeEvent(self, ev: Any) -> None:
        super().resizeEvent(ev)
        self._update_plot_labels()

    def _update_plot_labels(self) -> None:
        # generate plot labels by testing character-width points in view space and using bisect to turn those
        # into data indices, which makes this mostly (outside the log-factor of bisect) runtime independent
        # of the data set - it should handle very large datasets just as performantly
        for label in self._curves_labels:
            self.removeItem(label)
        self._curves_labels = []

        if len(self._edges) == 0 or self._data is None:  # nothing to be done
            return

        sample_label = pg.TextItem("00")  # get character width, assumed boundingRect in screen coordinates
        label_bounds_data = cast(QRect, self.mapRectToView(sample_label.boundingRect()))  # convert to data coordinates
        min_data_width = label_bounds_data.width()

        test_point_count = int((self.viewRect().right() - self.viewRect().left()) / label_bounds_data.width())
        # limit max points, otherwise breaks on excess zoom, also floor at 2 to avoid div0
        test_point_count = max(2, min(1024, test_point_count))
        test_point_span = (self.viewRect().right() - self.viewRect().left()) / (test_point_count - 1)  # fenceposting
        edge_index_min = bisect.bisect_left(self._edges, self.viewRect().left())
        edge_index_max = bisect.bisect_right(self._edges, self.viewRect().right())
        prev_edge_index: Optional[int] = None
        for test_point_i in range(test_point_count):
            test_data_pos = self.viewRect().left() + test_point_span * test_point_i
            # note, bisect left returns the first point at or AFTER the test point (insertion point)
            test_edge_index = bisect.bisect_left(self._edges, test_data_pos, lo=edge_index_min, hi=edge_index_max)
            if test_edge_index == prev_edge_index:
                continue
            prev_edge_index = test_edge_index
            if test_edge_index % 2 == 0:  # only keep transition edges
                continue
            assert test_edge_index > 0

            left_edge = self._edges[test_edge_index - 1]
            right_edge = self._edges[test_edge_index]
            if left_edge < self.viewRect().left() <= right_edge:  # clip left side to viewport
                left_edge = self.viewRect().left()
            if right_edge == self._edges[-1]:  # right side is unbounded
                right_edge = float("inf")
            held_data_width = right_edge - left_edge
            if held_data_width < min_data_width:  # quick test against minimum width
                continue

            data_index = bisect.bisect_left(self._data[0], left_edge)
            data_value = self._data[1][data_index]
            label = pg.TextItem(data_value, anchor=(0, 0.5))
            label.setColor(self._color.darker())
            label_width = cast(QRect, self.mapRectToView(label.boundingRect())).width()
            if held_data_width >= label_width:
                label.setPos(QPointF(left_edge, 0))
                self.addItem(label)
                self._curves_labels.append(label)
